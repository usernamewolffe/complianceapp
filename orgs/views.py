# orgs/views.py
from __future__ import annotations

import logging
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.urls import reverse
from django.http import HttpResponseForbidden
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST, require_http_methods
from django.shortcuts import get_object_or_404, render, redirect
from django.template import TemplateDoesNotExist

from rest_framework import viewsets, decorators, response, status, permissions as drf_permissions

# Models / forms / permissions / serializers
from .models import Org, Membership as MembershipModel, OrgInvite, Site
from .forms import SiteForm
from .permissions import Membership as MembershipPermission, RequireRole

# Optional Org serializer fallback (if not already defined)
try:
    from .serializers import OrgSerializer  # type: ignore[attr-defined]
except ImportError:  # pragma: no cover
    from rest_framework import serializers
    class OrgSerializer(serializers.ModelSerializer):
        class Meta:
            model = Org
            fields = "__all__"

from .serializers import OrgInviteSerializer, MembershipSerializer

# Guard helpers
from orgs.logic.guards import (
    GuardError,
    ensure_owner,
    guard_role_change,
    guard_toggle_active,
)

log = logging.getLogger(__name__)
User = get_user_model()


# --------------------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------------------
def _require_member(request, org: Org) -> bool:
    """User must be an active member of the org."""
    return MembershipModel.objects.filter(org=org, user=request.user, is_active=True).exists()

def _can_manage_sites(request, org: Org) -> bool:
    m = MembershipModel.objects.filter(org=org, user=request.user, is_active=True).first()
    return bool(m and m.role in (MembershipModel.OWNER, MembershipModel.ADMIN))


# ======================================================================================
# API: /api/me  (current user + active memberships)
# ======================================================================================
@decorators.api_view(["GET"])
@decorators.permission_classes([drf_permissions.IsAuthenticated])
def me_view(request):
    user = request.user
    memberships = (
        MembershipModel.objects.filter(user=user, is_active=True)
        .select_related("org")
        .values("org_id", "org__name", "role")
    )
    return response.Response(
        {
            "id": user.id,
            "username": getattr(user, "username", None),
            "email": getattr(user, "email", None),
            "memberships": [
                {"org_id": m["org_id"], "org_name": m["org__name"], "role": m["role"]}
                for m in memberships
            ],
        }
    )


# ======================================================================================
# API: Org CRUD + members + invite (DRF)
# ======================================================================================
class OrgViewSet(viewsets.ModelViewSet):
    """
    Org CRUD with membership-aware permissions.
    - list/retrieve: authenticated; limited to orgs you belong to
    - create: authenticated; creator becomes OWNER
    - update/partial_update/destroy/invite: require ADMIN+ on that org
    - members: list active members for the org
    """
    queryset = Org.objects.all()
    serializer_class = OrgSerializer
    lookup_field = "pk"

    def get_queryset(self):
        user = self.request.user
        if not user.is_authenticated:
            return Org.objects.none()
        return Org.objects.filter(
            memberships__user=user, memberships__is_active=True
        ).distinct()

    def get_permissions(self):
        if self.action in {"list", "retrieve", "members", "create"}:
            return [drf_permissions.IsAuthenticated()]
        # write operations on an existing org need admin+
        return [drf_permissions.IsAuthenticated(), RequireRole("admin")]

    def perform_create(self, serializer):
        org = serializer.save()
        if self.request.user.is_authenticated:
            MembershipModel.objects.get_or_create(
                org=org,
                user=self.request.user,
                defaults={
                    "role": MembershipModel.OWNER,
                    "is_active": True,
                    "accepted_at": timezone.now(),
                },
            )

    @decorators.action(
        detail=True,
        methods=["get"],
        permission_classes=[drf_permissions.IsAuthenticated, MembershipPermission],
    )
    def members(self, request, *args, **kwargs):
        org = self.get_object()
        qs = (
            MembershipModel.objects.filter(org=org, is_active=True)
            .select_related("user")
            .order_by("role", "user__username")
        )
        return response.Response(MembershipSerializer(qs, many=True).data)

    @decorators.action(
        detail=True,
        methods=["post"],
        permission_classes=[drf_permissions.IsAuthenticated, RequireRole("admin")],
    )
    def invite(self, request, *args, **kwargs):
        org = self.get_object()
        email = (request.data.get("email") or "").strip()
        role = (request.data.get("role") or MembershipModel.MEMBER).lower()

        if not email:
            return response.Response({"detail": "email required"}, status=400)
        if role not in dict(MembershipModel.ROLES):
            return response.Response({"detail": "invalid role"}, status=400)

        inv = OrgInvite.objects.create(
            email=email, org=org, role=role, invited_by=request.user
        )
        # TODO: send email with inv.token
        return response.Response(OrgInviteSerializer(inv).data, status=201)

@login_required
@require_POST
def org_invite_create(request, org_id):
    org = get_object_or_404(Org, id=org_id)

    # Only owners/admins can invite
    actor = MembershipModel.objects.filter(org=org, user=request.user, is_active=True).first()
    if not actor or actor.role not in (MembershipModel.OWNER, MembershipModel.ADMIN):
        return render_members_block(request, org, error="Only owners or admins can send invitations.")

    email = (request.POST.get("email") or "").strip()
    role = (request.POST.get("role") or MembershipModel.MEMBER).lower()

    if not email:
        return render_members_block(request, org, error="Email is required.")
    if role not in dict(MembershipModel.ROLES):
        return render_members_block(request, org, error="Invalid role.")

    # Prevent duplicate memberships / overlapping invites
    if MembershipModel.objects.filter(org=org, user__email=email).exists():
        return render_members_block(request, org, error="That user is already a member.")
    if OrgInvite.objects.filter(
        org=org,
        email=email,
        cancelled_at__isnull=True,
        used_at__isnull=True,
        expires_at__gte=timezone.now(),
    ).exists():
        return render_members_block(request, org, error="There is already a pending invite for that email.")

    OrgInvite.objects.create(email=email, org=org, role=role, invited_by=request.user)
    return render_members_block(request, org, ok=True)

@login_required
@require_POST
def invitation_cancel(request, org_id, inv_id):
    org = get_object_or_404(Org, id=org_id)

    # Only owners/admins can cancel
    actor = MembershipModel.objects.filter(org=org, user=request.user, is_active=True).first()
    if not actor or actor.role not in (MembershipModel.OWNER, MembershipModel.ADMIN):
        return render_members_block(request, org, error="Only owners or admins can cancel invitations.")

    inv = get_object_or_404(OrgInvite, org=org, id=inv_id)
    is_pending = not inv.used_at and not inv.cancelled_at and inv.expires_at >= timezone.now()
    if not is_pending:
        return render_members_block(request, org, error="Only pending invitations can be cancelled.")

    inv.cancelled_at = timezone.now()
    inv.save(update_fields=["cancelled_at"])
    return render_members_block(request, org, ok=True)


@login_required
@require_POST
def invitation_resend(request, org_id, inv_id):
    org = get_object_or_404(Org, id=org_id)

    # Only owners/admins can resend
    actor = MembershipModel.objects.filter(org=org, user=request.user, is_active=True).first()
    if not actor or actor.role not in (MembershipModel.OWNER, MembershipModel.ADMIN):
        return render_members_block(request, org, error="Only owners or admins can resend invitations.")

    inv = get_object_or_404(OrgInvite, org=org, id=inv_id)
    is_pending = not inv.used_at and not inv.cancelled_at
    if not is_pending:
        return render_members_block(request, org, error="Only pending invitations can be resent.")

    inv.expires_at = timezone.now() + timezone.timedelta(days=7)
    inv.save(update_fields=["expires_at"])
    return render_members_block(request, org, ok=True)

# ======================================================================================
# API: Accept invite
# ======================================================================================
class AcceptInviteViewSet(viewsets.ViewSet):
    """
    POST /api/invites/accept/ { "token": "<token>" }
    Requires authentication.
    """
    permission_classes = [drf_permissions.IsAuthenticated]

    @decorators.action(detail=False, methods=["post"])
    def accept(self, request):
        token = request.data.get("token")
        if not token:
            return response.Response({"detail": "token required"}, status=400)

        invite = get_object_or_404(OrgInvite, token=token)

        if invite.used_at:
            return response.Response({"detail": "Invite already used."}, status=400)
        if invite.expires_at < timezone.now():
            return response.Response({"detail": "Invite expired."}, status=400)

        membership, created = MembershipModel.objects.get_or_create(
            org=invite.org,
            user=request.user,
            defaults={
                "role": invite.role,
                "invited_by": invite.invited_by,
                "invited_at": timezone.now(),
                "accepted_at": timezone.now(),
                "is_active": True,
            },
        )
        if not created and membership.role != invite.role:
            membership.role = invite.role
            membership.accepted_at = membership.accepted_at or timezone.now()
            membership.is_active = True
            membership.save()

        invite.used_at = timezone.now()
        invite.save(update_fields=["used_at"])

        return response.Response(
            {"ok": True, "org": invite.org.id, "role": membership.role},
            status=status.HTTP_200_OK,
        )


# ======================================================================================
# UI helpers / block renderer (members)
# ======================================================================================
def render_members_block(request, org, *, ok=None, error=None):
    acting = MembershipModel.objects.filter(org=org, user=request.user).first()
    members = (
        MembershipModel.objects.filter(org=org)
        .select_related("user")
        .order_by("user__username")
    )
    invitations = OrgInvite.objects.filter(org=org).order_by("-expires_at")
    ctx = {
        "org": org,
        "members": members,
        "invitations": invitations,
        "roles": MembershipModel.ROLES,
        "acting_role": acting.role if acting else None,
        "ok": ok,
        "error": error,
    }
    return render(request, "ui/partials/_members.html", ctx)


@login_required
def org_members_block(request, org_id):
    """HTMX endpoint that renders the members block."""
    org = get_object_or_404(Org, id=org_id)
    if not _require_member(request, org):
        return HttpResponseForbidden("You don't have access to this organisation.")
    return render_members_block(request, org)


@login_required
def org_members_page(request, org_id):
    """Full page that shows the members block (bookmarkable)."""
    org = get_object_or_404(Org, id=org_id)
    if not _require_member(request, org):
        return HttpResponseForbidden("You don't have access to this organisation.")
    return render_members_block(request, org)


# ======================================================================================
# UI: Role change / activation with explicit precedence
# ======================================================================================
def _actor_member(request, org_id):
    return get_object_or_404(MembershipModel, org_id=org_id, user_id=request.user.id)

def _target_member(org_id, member_id):
    return get_object_or_404(MembershipModel, org_id=org_id, id=member_id)

def _is_last_active_owner(member: MembershipModel) -> bool:
    return (
        member.role == MembershipModel.OWNER
        and member.is_active
        and MembershipModel.objects.filter(
            org=member.org, role=MembershipModel.OWNER, is_active=True
        ).count() == 1
    )

@login_required
@require_POST
def org_member_update(request, org_id, member_id):
    org = get_object_or_404(Org, pk=org_id)
    actor = _actor_member(request, org_id)
    member = _target_member(org_id, member_id)
    new_role = (request.POST.get("role") or "").lower()

    order = {MembershipModel.MEMBER: 1, MembershipModel.ADMIN: 2, MembershipModel.OWNER: 3}
    lowering = order.get(new_role, 0) < order.get(member.role, 0)
    self_action = actor.user_id == member.user_id

    if lowering and member.role == MembershipModel.OWNER and _is_last_active_owner(member):
        return render_members_block(request, org, error="You can’t remove/demote the last Owner in this organisation.")

    if self_action and lowering:
        return render_members_block(request, org, error="You can’t lower your own role.")

    try:
        guard_role_change(MembershipModel.objects, actor, member, new_role)
    except GuardError as e:
        return render_members_block(request, org, error=str(e))

    if new_role != member.role:
        member.role = new_role
        member.save(update_fields=["role"])
    return render_members_block(request, org, ok=True)

@login_required
@require_POST
def org_member_toggle(request, org_id, member_id):
    org = get_object_or_404(Org, pk=org_id)
    actor = _actor_member(request, org_id)
    member = _target_member(org_id, member_id)
    new_active = (request.POST.get("active") or "").lower() == "true"

    self_action = actor.user_id == member.user_id

    if not new_active and _is_last_active_owner(member):
        return render_members_block(request, org, error="You can’t deactivate the last Owner in this organisation.")

    if self_action and not new_active:
        return render_members_block(request, org, error="You can’t deactivate your own account in this organisation.")

    try:
        guard_toggle_active(MembershipModel.objects, actor, member, new_active)
    except GuardError as e:
        return render_members_block(request, org, error=str(e))

    if member.is_active != new_active:
        member.is_active = new_active
        member.save(update_fields=["is_active"])
    return render_members_block(request, org, ok=True)


# ======================================================================================
# UI: Sites block + actions
# ======================================================================================
@login_required
@require_GET
def org_sites_block(request, org_id):
    """HTMX endpoint: render the Sites block for an org."""
    org = get_object_or_404(Org, pk=org_id)
    if not _require_member(request, org):
        return HttpResponseForbidden("You don't have access to this organisation.")

    sites = org.sites.order_by("name")
    can_manage_sites = _can_manage_sites(request, org)

    return render(
        request,
        "ui/partials/_sites.html",
        {"org": org, "sites": sites, "can_manage_sites": can_manage_sites},
    )


@login_required
@require_http_methods(["GET", "POST"])
def site_create(request, org_id):
    """
    GET  -> returns content-only form partial into the create modal body
    POST -> on success: returns refreshed #sites-block (via HX headers)
            on invalid: returns the form partial (with errors) back into the modal body
    """
    org = get_object_or_404(Org, pk=org_id)
    if not _require_member(request, org):
        return HttpResponseForbidden("You don't have access to this organisation.")

    if request.method == "POST":
        form = SiteForm(request.POST)
        if form.is_valid():
            site = form.save(commit=False)
            site.org = org
            site.save()

            sites = Site.objects.filter(org=org).order_by("name")
            resp = render(request, "ui/partials/_sites.html", {
                "org": org,
                "sites": sites,
                "can_manage_sites": _can_manage_sites(request, org),
            })
            # Tell HTMX to retarget the swap at the sites list (not the modal body)
            resp["HX-Retarget"] = "#sites-block"
            resp["HX-Reswap"] = "outerHTML"
            return resp

        # invalid -> fall through to re-render the form into the modal body (200)

    else:
        form = SiteForm()

    return render(request, "ui/partials/_site_create_form.html", {"org": org, "form": form})


@login_required
@require_POST
def site_delete(request, org_id, site_id):
    """POST-only, returns refreshed Sites block (safe delete)."""
    org = get_object_or_404(Org, pk=org_id)
    if not _require_member(request, org):
        return HttpResponseForbidden("You don't have access to this organisation.")

    site = get_object_or_404(Site, pk=site_id, org=org)

    # Optional safety: block deletion if incidents exist
    if hasattr(site, "incidents") and site.incidents.exists():
        sites = Site.objects.filter(org=org).order_by("name")
        return render(
            request,
            "ui/partials/_sites.html",
            {
                "org": org,
                "sites": sites,
                "can_manage_sites": _can_manage_sites(request, org),
                "error": f"Cannot delete '{site.name}' – incidents exist.",
            },
        )

    site.delete()

    sites = Site.objects.filter(org=org).order_by("name")
    return render(
        request,
        "ui/partials/_sites.html",
        {"org": org, "sites": sites, "can_manage_sites": _can_manage_sites(request, org)},
    )


@login_required
@require_http_methods(["GET", "POST"])
def site_edit(request, org_id, site_id):
    """
    GET:
      - If HTMX: return a modal snippet (dialog + form) appended to <body>.
      - Else: return a full page 'ui/site_edit.html'.
    POST:
      - Save and redirect back to ?next=… (or org detail) on normal request.
      - If HTMX POST, you can adapt to return a refreshed sites block (not used by default here).
    """
    org = get_object_or_404(Org, pk=org_id)
    if not _require_member(request, org):
        return HttpResponseForbidden("You don't have access to this organisation.")

    site = get_object_or_404(Site, pk=site_id, org=org)
    default_next = reverse("orgs:org-detail", args=[org.id])  # ensure this URL name exists
    next_url = request.GET.get("next") or request.POST.get("next") or default_next

    if request.method == "POST":
        if "cancel" in request.POST:
            return redirect(next_url)

        form = SiteForm(request.POST, instance=site)
        if form.is_valid():
            form.save()
            return redirect(next_url)
    else:
        form = SiteForm(instance=site)

    # inside site_edit (after form.is_valid() and form.save())
    if request.headers.get("HX-Request"):
        sites = Site.objects.filter(org=org).order_by("name")
        resp = render(request, "ui/partials/_sites.html", {
            "org": org,
            "sites": sites,
            "can_manage_sites": _can_manage_sites(request, org),
        })
        # (hx-target already points to #sites-block, so no headers are strictly needed)
        # If you prefer headers-based retargeting, you can add:
        # resp["HX-Retarget"] = "#sites-block"
        # resp["HX-Reswap"] = "outerHTML"
        return resp

    # non-HTMX:
    return redirect(next_url)




