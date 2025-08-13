# orgs/views.py
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.shortcuts import get_object_or_404, render
from django.http import JsonResponse, HttpResponseForbidden
from django.views.decorators.http import require_http_methods, require_POST

from rest_framework import viewsets, decorators, response, status, permissions as drf_permissions
from rest_framework.decorators import api_view, permission_classes

# Models/permissions (avoid name clashes by aliasing)
from .models import Org, Membership as MembershipModel, OrgInvite
from .permissions import Membership as MembershipPermission, RequireRole
from .serializers import OrgInviteSerializer, MembershipSerializer

# If you already have an OrgSerializer in orgs/serializers.py, import it.
# If not, this minimal inline fallback keeps things working.
try:
    from .serializers import OrgSerializer  # type: ignore[attr-defined]
except ImportError:  # pragma: no cover
    from rest_framework import serializers
    class OrgSerializer(serializers.ModelSerializer):
        class Meta:
            model = Org
            fields = "__all__"

User = get_user_model()


# --------------------------------------------------------------------------------------
# API: current user + memberships
# --------------------------------------------------------------------------------------
@api_view(["GET"])
@permission_classes([drf_permissions.IsAuthenticated])
def me_view(request):
    """Return current user info + memberships."""
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


# --------------------------------------------------------------------------------------
# API: Org CRUD
# --------------------------------------------------------------------------------------
class OrgViewSet(viewsets.ModelViewSet):
    """
    Org CRUD with membership-aware permissions.
    - list/retrieve: must be authenticated; results limited to orgs you belong to
    - create: any authenticated user; creator becomes OWNER
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
        return (
            Org.objects.filter(memberships__user=user, memberships__is_active=True)
            .distinct()
        )

    def get_permissions(self):
        if self.action in {"list", "retrieve", "members"}:
            return [drf_permissions.IsAuthenticated()]
        if self.action in {"create"}:
            return [drf_permissions.IsAuthenticated()]
        # write operations on an existing org need admin+
        return [drf_permissions.IsAuthenticated(), RequireRole("admin")]

    def perform_create(self, serializer):
        """On create, save org and grant creator OWNER membership."""
        org = serializer.save()
        if self.request.user.is_authenticated:
            MembershipModel.objects.get_or_create(
                org=org,
                user=self.request.user,
                defaults={
                    "role": MembershipModel.OWNER,   # "owner"
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
        email = request.data.get("email")
        role = request.data.get("role", MembershipModel.MEMBER)

        if not email:
            return response.Response({"detail": "email required"}, status=400)
        if role not in dict(MembershipModel.ROLES):
            return response.Response({"detail": "invalid role"}, status=400)

        inv = OrgInvite.objects.create(
            email=email, org=org, role=role, invited_by=request.user
        )
        # TODO: send email containing a link with inv.token
        return response.Response(OrgInviteSerializer(inv).data, status=201)


# --------------------------------------------------------------------------------------
# API: Accept invite
# --------------------------------------------------------------------------------------
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


# --------------------------------------------------------------------------------------
# UI helpers / block renderer
# --------------------------------------------------------------------------------------
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
    # Only allow users who belong to this org
    if not MembershipModel.objects.filter(org=org, user=request.user, is_active=True).exists():
        return HttpResponseForbidden("You don't have access to this organisation.")
    return render_members_block(request, org)


# --------------------------------------------------------------------------------------
# UI: Role change / activation with server-side safeguards
# --------------------------------------------------------------------------------------
from orgs.logic.guards import GuardError, guard_role_change, guard_toggle_active, ensure_owner  # noqa: E402


def _actor_member(request, org_id):
    return get_object_or_404(MembershipModel, org_id=org_id, user_id=request.user.id)


def _target_member(org_id, member_id):
    return get_object_or_404(MembershipModel, org_id=org_id, id=member_id)


@require_http_methods(["PATCH", "POST"])  # HTMX may POST as fallback
def org_member_update(request, org_id, member_id):
    actor = _actor_member(request, org_id)
    target = _target_member(org_id, member_id)
    org = target.org

    new_role = (request.POST.get("role") or request.GET.get("role") or "").lower()
    if new_role not in dict(MembershipModel.ROLES):
        return render_members_block(request, org, error="Invalid role.")

    try:
        guard_role_change(MembershipModel.objects, actor, target, new_role)
    except GuardError as e:
        return render_members_block(request, org, error=str(e))

    target.role = new_role
    target.save(update_fields=["role"])
    return render_members_block(request, org, ok=True)


@require_http_methods(["POST"])
def org_member_toggle(request, org_id, member_id):
    actor = _actor_member(request, org_id)
    target = _target_member(org_id, member_id)
    org = target.org

    # Accept either "active" (template) or "is_active"
    raw = request.POST.get("active", request.POST.get("is_active", ""))
    new_active = str(raw).lower() in ("1", "true", "yes", "on")

    try:
        guard_toggle_active(MembershipModel.objects, actor, target, new_active)
    except GuardError as e:
        return render_members_block(request, org, error=str(e))

    target.is_active = new_active
    target.save(update_fields=["is_active"])
    return render_members_block(request, org, ok=True)


# --------------------------------------------------------------------------------------
# UI: Invitation actions (Cancel / Resend) and Create
# --------------------------------------------------------------------------------------
@require_POST
def invitation_cancel(request, org_id, inv_id):
    actor = _actor_member(request, org_id)
    try:
        ensure_owner(actor)
    except GuardError as e:
        org = get_object_or_404(Org, id=org_id)
        return render_members_block(request, org, error=str(e))

    inv = get_object_or_404(OrgInvite, org_id=org_id, id=inv_id)

    # Only pending (not used/cancelled/expired)
    is_pending = not inv.used_at and not inv.cancelled_at and (inv.expires_at >= timezone.now())
    if not is_pending:
        org = get_object_or_404(Org, id=org_id)
        return render_members_block(request, org, error="Only pending invitations can be cancelled.")

    inv.cancelled_at = timezone.now()
    inv.save(update_fields=["cancelled_at"])
    org = get_object_or_404(Org, id=org_id)
    return render_members_block(request, org, ok=True)


@require_POST
def invitation_resend(request, org_id, inv_id):
    actor = _actor_member(request, org_id)
    try:
        ensure_owner(actor)
    except GuardError as e:
        org = get_object_or_404(Org, id=org_id)
        return render_members_block(request, org, error=str(e))

    inv = get_object_or_404(OrgInvite, org_id=org_id, id=inv_id)

    # Only pending can be resent
    is_pending = not inv.used_at and not inv.cancelled_at and (inv.expires_at >= timezone.now())
    if not is_pending:
        org = get_object_or_404(Org, id=org_id)
        return render_members_block(request, org, error="Only pending invitations can be resent.")

    # TODO: send the email with inv.token using your mailer
    inv.expires_at = timezone.now() + timezone.timedelta(days=7)  # extend validity on resend
    inv.save(update_fields=["expires_at"])
    org = get_object_or_404(Org, id=org_id)
    return render_members_block(request, org, ok=True)


@login_required
def org_members_page(request, org_id):
    """Full page that shows the members block (handy bookmarkable page)."""
    org = get_object_or_404(Org, id=org_id)

    # Only allow users who belong to this org
    if not MembershipModel.objects.filter(org=org, user=request.user, is_active=True).exists():
        return HttpResponseForbidden("You don't have access to this organisation.")

    # Build the same context your block expects
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
        "ok": None,
        "error": None,
    }
    return render(request, "ui/members_page.html", ctx)


@require_POST
def org_invite_create(request, org_id):
    """Create an OrgInvite and re-render the members block."""
    org = get_object_or_404(Org, id=org_id)
    actor = _actor_member(request, org_id)

    # owners and admins may invite
    if not actor or actor.role not in (MembershipModel.OWNER, MembershipModel.ADMIN):
        return render_members_block(request, org, error="Only owners or admins can send invitations.")

    email = (request.POST.get("email") or "").strip()
    role = (request.POST.get("role") or MembershipModel.MEMBER).lower()

    if not email:
        return render_members_block(request, org, error="Email is required.")
    if role not in dict(MembershipModel.ROLES):
        return render_members_block(request, org, error="Invalid role.")

    # Optional: avoid duplicate membership / pending invite
    if MembershipModel.objects.filter(org=org, user__email=email).exists():
        return render_members_block(request, org, error="That user is already a member.")
    if OrgInvite.objects.filter(
        org=org, email=email,
        cancelled_at__isnull=True, used_at__isnull=True,
        expires_at__gte=timezone.now()
    ).exists():
        return render_members_block(request, org, error="There is already a pending invite for that email.")

    OrgInvite.objects.create(email=email, org=org, role=role, invited_by=request.user)
    # TODO: send email with invite.token
    return render_members_block(request, org, ok=True)
