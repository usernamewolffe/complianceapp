# ui/views.py
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.views.decorators.http import (
    require_http_methods,
    require_GET,
    require_POST,
)

from orgs.models import Org, Membership, OrgInvite
from compliance_app.models import ComplianceRecord
from .forms import OrgCreateForm, ComplianceRecordCreateForm
from django.views.decorators.http import require_POST
from django.http import HttpResponseBadRequest

from django.shortcuts import redirect, render
from django.contrib.auth.decorators import login_required
from orgs.models import Membership

from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from orgs.models import Membership as MembershipModel, Org, OrgInvite


# ---------- helpers ----------
def home(request):
    if request.user.is_authenticated:
        m = (Membership.objects
             .filter(user=request.user, is_active=True)
             .select_related("org")
             .first())
    else:
        m = None
    if m:
        return redirect("org-detail", org_id=m.org_id)
    return render(request, "ui/home .html")  # create a tiny template or swap to a redirect you prefer

def _require_member(user, org: Org) -> bool:
    """Is the user an active member of this org?"""
    return Membership.objects.filter(org=org, user=user, is_active=True).exists()

def _acting_role(user, org: Org):
    m = Membership.objects.filter(org=org, user=user, is_active=True).first()
    return m.role if m else None

def _owner_count(org: Org) -> int:
    return Membership.objects.filter(
        org=org, role=Membership.OWNER, is_active=True
    ).count()

def _render_members_panel(request, org: Org, extra_ctx: dict | None = None):
    members = (
        Membership.objects.filter(org=org, is_active=True)
        .select_related("user")
        .order_by("role", "user__username")
    )
    invitations = OrgInvite.objects.filter(org=org, used_at__isnull=True).order_by("-expires_at")
    ctx = {
        "org": org,
        "members": members,
        "invitations": invitations,   # UI wording
        "invites": invitations,       # backward-compat if template still references 'invites'
        "roles": Membership.ROLES,
        "acting_role": _acting_role(request.user, org),
    }
    if extra_ctx:
        ctx.update(extra_ctx)
    return render(request, "ui/partials/_members.html", ctx)


def _acting_role(user, org: Org) -> str:
    return (
        Membership.objects.filter(org=org, user=user, is_active=True)
        .values_list("role", flat=True)
        .first()
        or ""
    )

def _members_panel_context(request, org: Org, *, ok=False, error=None):
    members = (
        Membership.objects.filter(org=org)
        .select_related("user")
        .order_by("role", "user__username")
    )
    invitations = OrgInvite.objects.filter(org=org, used_at__isnull=True).order_by("-expires_at")
    return {
        "org": org,
        "members": members,
        "invitations": invitations,
        "roles": Membership.ROLES,
        "acting_role": _acting_role(request.user, org),
        "ok": ok,
        "error": error,
    }


# ---------- dashboard ----------
@login_required
def dashboard(request):
    # The user's orgs (via memberships)
    orgs = (
        Org.objects.filter(memberships__user=request.user, memberships__is_active=True)
        .order_by("name")
        .distinct()
    )

    # Latest 10 records across those orgs
    records = (
        ComplianceRecord.objects.select_related("org")
        .filter(org__in=orgs)
        .order_by("-last_updated")[:10]
    )

    # Choices for inline status dropdowns
    status_choices = ComplianceRecord._meta.get_field("status").choices
    valid_status_values = {value for value, _ in status_choices}

    # Default (GET) forms
    org_form = OrgCreateForm()
    record_form = ComplianceRecordCreateForm(user=request.user)

    if request.method == "POST":

        # CREATE ORG
        if "create_org" in request.POST:
            org_form = OrgCreateForm(request.POST)
            if org_form.is_valid():
                new_org = org_form.save(owner=request.user)
                messages.success(request, f"Created organisation “{new_org.name}”.")
                return redirect("dashboard")
            messages.error(request, "Please fix the errors below.")

        # CREATE RECORD (dashboard quick-add)
        elif "create_record" in request.POST:
            record_form = ComplianceRecordCreateForm(request.POST, user=request.user)
            if record_form.is_valid():
                new_record = record_form.save()
                messages.success(
                    request, f"Created compliance record for “{new_record.org.name}”."
                )
                return redirect("dashboard")
            messages.error(request, "Please fix the errors below.")

        # UPDATE STATUS (inline) — membership-gated
        elif "update_status" in request.POST:
            record_id = request.POST.get("record_id")
            new_status = request.POST.get("status")
            if new_status not in valid_status_values:
                messages.error(request, "Invalid status.")
                return redirect("dashboard")

            record = get_object_or_404(
                ComplianceRecord.objects.select_related("org"),
                id=record_id,
                org__memberships__user=request.user,
                org__memberships__is_active=True,
            )
            if record.status != new_status:
                record.status = new_status
                record.save()  # auto-updates last_updated
                messages.success(
                    request,
                    f"Updated status to “{dict(status_choices).get(new_status, new_status)}”.",
                )
            else:
                messages.success(request, "Status unchanged.")
            return redirect("dashboard")

        # DELETE ORG — admin/owner only
        elif "delete_org" in request.POST:
            org_id = request.POST.get("delete_org")
            org = get_object_or_404(
                Org,
                id=org_id,
                memberships__user=request.user,
                memberships__is_active=True,
                memberships__role__in=[Membership.ADMIN, Membership.OWNER],
            )
            org_name = org.name
            org.delete()
            messages.success(request, f"Deleted organisation “{org_name}”.")
            return redirect("dashboard")

        # DELETE RECORD — membership-gated
        elif "delete_record" in request.POST:
            record_id = request.POST.get("delete_record")
            record = get_object_or_404(
                ComplianceRecord.objects.select_related("org"),
                id=record_id,
                org__memberships__user=request.user,
                org__memberships__is_active=True,
            )
            rec_name = record.requirement
            record.delete()
            messages.success(request, f"Deleted compliance record “{rec_name}”.")
            return redirect("dashboard")

    return render(
        request,
        "ui/dashboard.html",
        {
            "orgs": orgs,
            "records": records,
            "form": org_form,
            "record_form": record_form,
            "status_choices": status_choices,
        },
    )


# ---------- org page + inline edits ----------
@login_required
def org_detail(request, org_id):
    org = get_object_or_404(Org, pk=org_id)
    if not _require_member(request.user, org):
        return HttpResponseForbidden("Not a member")

    # records + pagination
    records = ComplianceRecord.objects.filter(org=org).order_by("-id")
    page = Paginator(records, 25).get_page(request.GET.get("page"))

    # members + invitations + acting role
    members = (
        Membership.objects.filter(org=org, is_active=True)
        .select_related("user")
        .order_by("role", "user__username")
    )
    invitations = OrgInvite.objects.filter(org=org, used_at__isnull=True).order_by("-expires_at")

    return render(
        request,
        "ui/org_detail.html",
        {
            "org": org,
            "page": page,
            "members": members,
            "invitations": invitations,  # preferred wording
            "invites": invitations,      # temporary alias if any template still says 'invites'
            "roles": Membership.ROLES,
            "acting_role": _acting_role(request.user, org),
        },
    )

@require_POST
@login_required
def org_member_toggle_active(request, org_id, member_id):
    org = get_object_or_404(Org, pk=org_id)
    if not _require_member(request.user, org):
        return HttpResponseForbidden()

    acting = Membership.objects.filter(org=org, user=request.user, is_active=True).first()
    if not acting or acting.role != Membership.OWNER:
        return HttpResponseForbidden("Owners only.")

    target = get_object_or_404(Membership, pk=member_id, org=org)

    active_str = (request.POST.get("active") or "").lower()
    if active_str not in {"true", "false"}:
        return _render_members_panel(request, org, {"error": "Invalid active flag."})
    make_active = active_str == "true"

    # safety: cannot deactivate yourself
    if (not make_active) and target.user_id == request.user.id:
        return _render_members_panel(request, org, {"error": "You can’t deactivate yourself."})

    # safety: cannot deactivate the last owner
    if (not make_active) and target.role == Membership.OWNER and _owner_count(org) <= 1:
        return _render_members_panel(request, org, {"error": "Cannot deactivate the last owner."})

    if target.is_active != make_active:
        target.is_active = make_active
        target.save(update_fields=["is_active"])

    return _render_members_panel(request, org, {"ok": True})


@require_http_methods(["GET"])
@login_required
def org_name_partial(request, org_id):
    org = get_object_or_404(Org, pk=org_id)
    if not _require_member(request.user, org):
        return HttpResponseForbidden()
    return render(request, "ui/partials/_org_name.html", {"org": org})


@require_http_methods(["GET", "POST"])
@login_required
def org_name_edit(request, org_id):
    org = get_object_or_404(Org, pk=org_id)
    if not _require_member(request.user, org):
        return HttpResponseForbidden()
    if request.method == "GET":
        return render(request, "ui/partials/_org_name_form.html", {"org": org})
    name = (request.POST.get("name") or "").strip()
    if not name:
        return render(
            request,
            "ui/partials/_org_name_form.html",
            {"org": org, "error": "Name is required"},
            status=400,
        )
    org.name = name
    org.save(update_fields=["name"])
    return render(request, "ui/partials/_org_name.html", {"org": org})


# ---------- record inline row / edit / delete / create ----------
@require_http_methods(["GET"])
@login_required
def record_row(request, pk):
    rec = get_object_or_404(ComplianceRecord, pk=pk)
    if not _require_member(request.user, rec.org):
        return HttpResponseForbidden()
    return render(request, "ui/partials/_record_row.html", {"rec": rec})


@require_http_methods(["GET", "POST"])
@login_required
def record_edit(request, pk):
    rec = get_object_or_404(ComplianceRecord, pk=pk)
    if not _require_member(request.user, rec.org):
        return HttpResponseForbidden()
    if request.method == "GET":
        return render(request, "ui/partials/_record_form.html", {"rec": rec})
    requirement = (request.POST.get("requirement") or "").strip()
    new_status = (request.POST.get("status") or "").strip()
    if not requirement:
        return render(
            request,
            "ui/partials/_record_form.html",
            {"rec": rec, "error": "Requirement is required"},
            status=400,
        )
    rec.requirement = requirement
    if new_status:
        rec.status = new_status
    rec.save(update_fields=["requirement", "status"])
    return render(request, "ui/partials/_record_row.html", {"rec": rec})


@require_http_methods(["POST"])
@login_required
def record_delete(request, pk):
    rec = get_object_or_404(ComplianceRecord, pk=pk)
    if not _require_member(request.user, rec.org):
        return HttpResponseForbidden()
    rec.delete()
    return HttpResponse("")


@require_http_methods(["GET", "POST"])
@login_required
def record_create(request, org_id):
    """Inline create on the org page (HTMX)."""
    org = get_object_or_404(Org, pk=org_id)
    if not _require_member(request.user, org):
        return HttpResponseForbidden()

    if request.method == "GET":
        return render(request, "ui/partials/_record_create_form.html", {"org": org})

    requirement = (request.POST.get("requirement") or "").strip()
    status_val = (request.POST.get("status") or "pending").strip()
    if not requirement:
        return render(
            request,
            "ui/partials/_record_create_form.html",
            {"org": org, "error": "Requirement is required.", "status_val": status_val},
            status=400,
        )

    rec = ComplianceRecord.objects.create(
        org=org, requirement=requirement, status=status_val
    )
    # Return the new row so HTMX can insert it into the table
    return render(request, "ui/partials/_record_row.html", {"rec": rec})


# ---------- members panel, invite, join ----------
@require_GET
@login_required
def org_members_partial(request, org_id):
    org = get_object_or_404(Org, pk=org_id)
    if not _require_member(request.user, org):
        return HttpResponseForbidden()

    # Role of current user (default to MEMBER if not found)
    acting_role = (
        Membership.objects.filter(
            org=org, user=request.user, is_active=True
        ).values_list("role", flat=True).first()
        or Membership.MEMBER
    )

    members = (
        Membership.objects.filter(org=org, is_active=True)
        .select_related("user")
        .order_by("role", "user__username")
    )

    invitations = OrgInvite.objects.filter(
        org=org, used_at__isnull=True
    ).order_by("-expires_at")

    return render(
        request,
        "ui/partials/_members.html",
        {
            "org": org,
            "members": members,
            "invitations": invitations,   # renamed from "invites"
            "roles": Membership.ROLES,
            "acting_role": acting_role,
        },
    )


@require_POST
@login_required
def org_member_update(request, org_id, member_id):
    """Owner can change a member's role (with safety checks)."""
    org = get_object_or_404(Org, pk=org_id)
    # Only owner can change roles
    if not Membership.objects.filter(org=org, user=request.user, is_active=True, role=Membership.OWNER).exists():
        return HttpResponseForbidden()

    m = get_object_or_404(Membership, pk=member_id, org=org)

    new_role = request.POST.get("role")
    valid_roles = set(dict(Membership.ROLES).keys())
    if new_role not in valid_roles:
        return render(
            request, "ui/partials/_members.html",
            _members_panel_context(request, org, error="Invalid role."),
            status=400,
        )

    # Safety: don't let last owner be demoted
    if m.role == Membership.OWNER and new_role != Membership.OWNER:
        owners = Membership.objects.filter(org=org, role=Membership.OWNER, is_active=True).exclude(id=m.id)
        if not owners.exists():
            return render(
                request, "ui/partials/_members.html",
                _members_panel_context(request, org, error="You must have at least one active owner."),
                status=400,
            )

    m.role = new_role
    m.save(update_fields=["role"])

    return render(request, "ui/partials/_members.html", _members_panel_context(request, org, ok=True))


@require_POST
@login_required
def org_member_toggle(request, org_id, member_id):
    """Owner can deactivate/reactivate a membership (with safety checks)."""
    org = get_object_or_404(Org, pk=org_id)
    if not Membership.objects.filter(org=org, user=request.user, is_active=True, role=Membership.OWNER).exists():
        return HttpResponseForbidden()

    m = get_object_or_404(Membership, pk=member_id, org=org)
    want_active = (request.POST.get("active") == "true")

    # Don't allow deactivating yourself
    if m.user_id == request.user.id and not want_active:
        return render(
            request, "ui/partials/_members.html",
            _members_panel_context(request, org, error="You can’t deactivate yourself."),
            status=400,
        )

    # Don't allow deactivating the last owner
    if m.role == Membership.OWNER and not want_active:
        owners = Membership.objects.filter(org=org, role=Membership.OWNER, is_active=True).exclude(id=m.id)
        if not owners.exists():
            return render(
                request, "ui/partials/_members.html",
                _members_panel_context(request, org, error="You must have at least one active owner."),
                status=400,
            )

    if m.is_active != want_active:
        m.is_active = want_active
        if want_active and not m.accepted_at:
            m.accepted_at = timezone.now()
        m.save(update_fields=["is_active", "accepted_at"])

    return render(request, "ui/partials/_members.html", _members_panel_context(request, org, ok=True))

@require_POST
@login_required
def member_update_role(request, org_id, membership_id):
    org = get_object_or_404(Org, pk=org_id)

    # only admins/owners may change roles
    if not Membership.objects.filter(
        org=org, user=request.user, is_active=True,
        role__in=[Membership.ADMIN, Membership.OWNER],
    ).exists():
        return HttpResponseForbidden()

    target = get_object_or_404(Membership, pk=membership_id, org=org, is_active=True)
    new_role = request.POST.get("role")

    # validate role
    valid_roles = {value for value, _ in Membership.ROLES}
    if new_role not in valid_roles:
        return HttpResponseBadRequest("Invalid role")

    # prevent demoting the last owner
    if target.role == Membership.OWNER and new_role != Membership.OWNER:
        owners = Membership.objects.filter(org=org, is_active=True, role=Membership.OWNER)
        if owners.count() == 1:
            return HttpResponseBadRequest("Cannot demote the last owner")

    # apply
    target.role = new_role
    target.save(update_fields=["role"])

    # re-render the members panel
    members = (
        Membership.objects.filter(org=org, is_active=True)
        .select_related("user")
        .order_by("role", "user__username")
    )
    invitations = OrgInvite.objects.filter(org=org, used_at__isnull=True).order_by("-expires_at")
    return render(
        request,
        "ui/partials/_members.html",
        {"org": org, "members": members, "invitations": invitations, "roles": Membership.ROLES},
    )


@require_POST
@login_required
def org_invite_create(request, org_id):
    org = get_object_or_404(Org, pk=org_id)
    # require admin+ to invite
    if not Membership.objects.filter(
        org=org,
        user=request.user,
        is_active=True,
        role__in=[Membership.ADMIN, Membership.OWNER],
    ).exists():
        return HttpResponseForbidden()
    email = (request.POST.get("email") or "").strip()
    role = request.POST.get("role") or Membership.MEMBER
    if not email or role not in dict(Membership.ROLES):
        return render(
            request,
            "ui/partials/_members.html",
            {
                "org": org,
                "members": [],
                "invitations": [],
                "roles": Membership.ROLES,
                "error": "Valid email and role required.",
            },
            status=400,
        )
    OrgInvite.objects.create(email=email, org=org, role=role, invited_by=request.user)
    # re-render the panel
    members = (
        Membership.objects.filter(org=org, is_active=True)
        .select_related("user")
        .order_by("role", "user__username")
    )
    invites = OrgInvite.objects.filter(org=org, used_at__isnull=True).order_by(
        "-expires_at"
    )
    return render(
        request,
        "ui/partials/_members.html",
        {
            "org": org,
            "members": members,
            "invitations": invites,
            "roles": Membership.ROLES,
            "ok": True,
        },
    )


@login_required
def join(request, token: str):
    """Accept an invitation (must be logged in)."""
    invite = get_object_or_404(OrgInvite, token=token)
    if invite.used_at:
        return render(
            request, "ui/join_result.html", {"error": "Invite already used."}, status=400
        )
    if invite.expires_at < timezone.now():
        return render(
            request, "ui/join_result.html", {"error": "Invite expired."}, status=400
        )

    m, created = Membership.objects.get_or_create(
        org=invite.org,
        user=request.user,
        defaults={
            "role": invite.role,
            "is_active": True,
            "invited_by": invite.invited_by,
            "invited_at": timezone.now(),
            "accepted_at": timezone.now(),
        },
    )
    if not created and m.role != invite.role:
        m.role = invite.role
        m.is_active = True
        m.accepted_at = m.accepted_at or timezone.now()
        m.save()

    invite.used_at = timezone.now()
    invite.save(update_fields=["used_at"])
    return render(request, "ui/join_result.html", {"org": invite.org})

@login_required
def home(request):
    # send signed-in users to their first org's members page
    m = (Membership.objects
         .filter(user=request.user, is_active=True)
         .select_related("org")
         .first())
    if m:
        return redirect("org-members-ui", org_id=m.org_id)
    # if user has no orgs yet, show your dashboard page
    return render(request, "ui/dashboard.html", {})

@login_required
def org_members_page(request, org_id):
    org = get_object_or_404(Org, id=org_id)
    # Only allow users who belong to this org
    if not MembershipModel.objects.filter(org=org, user=request.user, is_active=True).exists():
        return HttpResponseForbidden("You don't have access to this organisation.")

    # Build the same context the block uses
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
