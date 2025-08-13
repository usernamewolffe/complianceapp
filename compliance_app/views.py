# compliance_app/views.py
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_http_methods, require_POST

from rest_framework import viewsets, permissions, filters
from rest_framework.exceptions import PermissionDenied
from django_filters.rest_framework import DjangoFilterBackend
from drf_yasg.utils import swagger_auto_schema

from orgs.models import Org, Membership
from .models import ComplianceRecord
from .serializers import ComplianceRecordSerializer
from .filters import ComplianceRecordFilter


# --------------------------------------------------------------------------------------
# DRF API
# --------------------------------------------------------------------------------------
class ComplianceRecordViewSet(viewsets.ModelViewSet):
    """
    CRUD for compliance records, scoped to orgs the signed-in user belongs to.
    """
    serializer_class = ComplianceRecordSerializer
    permission_classes = [permissions.IsAuthenticated]
    queryset = ComplianceRecord.objects.none()  # for schema generation

    # Filtering / search / ordering
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = ComplianceRecordFilter
    filterset_fields = ["org", "status", "requirement", "last_updated"]
    search_fields = ["requirement", "org__name"]
    ordering_fields = ["last_updated", "requirement", "status", "id"]
    ordering = ["-last_updated"]

    def get_queryset(self):
        # drf-yasg sets this during schema generation
        if getattr(self, "swagger_fake_view", False):
            return ComplianceRecord.objects.none()

        user = getattr(self.request, "user", None)
        if not user or not user.is_authenticated:
            return ComplianceRecord.objects.none()

        # Records where the user is an active member of the org
        return (
            ComplianceRecord.objects
            .select_related("org")
            .filter(org__memberships__user=user, org__memberships__is_active=True)
            .distinct()
        )

    @swagger_auto_schema(operation_summary="List compliance records for your organisations")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    # Defense-in-depth: only allow create/update when user is ADMIN/OWNER on the org
    def _require_admin(self, org):
        has_role = Membership.objects.filter(
            org=org, user=self.request.user, is_active=True,
            role__in=(Membership.ADMIN, Membership.OWNER),
        ).exists()
        if not has_role:
            raise PermissionDenied("Admin or Owner role required.")

    def perform_create(self, serializer):
        org = serializer.validated_data.get("org")
        if not Membership.objects.filter(org=org, user=self.request.user, is_active=True).exists():
            raise PermissionDenied("You are not a member of this organisation.")
        self._require_admin(org)
        serializer.save()

    def perform_update(self, serializer):
        org = serializer.validated_data.get("org") or serializer.instance.org
        if not Membership.objects.filter(org=org, user=self.request.user, is_active=True).exists():
            raise PermissionDenied("You are not a member of this organisation.")
        self._require_admin(org)
        serializer.save()


# --------------------------------------------------------------------------------------
# UI (HTMX) block + actions
# --------------------------------------------------------------------------------------

def _status_choices():
    """
    Support either a Django choices tuple (STATUS_CHOICES) or an Enum class (.Status.choices).
    """
    if hasattr(ComplianceRecord, "STATUS_CHOICES"):
        return ComplianceRecord.STATUS_CHOICES
    if hasattr(ComplianceRecord, "Status") and hasattr(ComplianceRecord.Status, "choices"):
        return ComplianceRecord.Status.choices
    # Fallback: a minimal set
    return [("in_progress", "In progress"), ("done", "Done")]

def _valid_statuses():
    return {c[0] for c in _status_choices()}

def _is_member(user, org):
    return Membership.objects.filter(org=org, user=user, is_active=True).exists()

def _is_admin(user, org):
    return Membership.objects.filter(
        org=org, user=user, is_active=True, role__in=(Membership.ADMIN, Membership.OWNER)
    ).exists()

def _render_records_block(request, org, *, ok=None, error=None):
    records = ComplianceRecord.objects.filter(org=org).order_by("-id")
    ctx = {
        "org": org,
        "records": records,
        "statuses": _status_choices(),
        "ok": ok,
        "error": error,
    }
    return render(request, "ui/partials/_records.html", ctx)

# ---- Helpers ---------------------------------------------------------------

def _require_member(request, org_id):
    """Return (org, acting_membership) or (None, None) if forbidden."""
    org = get_object_or_404(Org, id=org_id)
    acting = Membership.objects.filter(org=org, user=request.user, is_active=True).first()
    if not acting:
        return None, None
    return org, acting

# ---- Blocks / Partials -----------------------------------------------------

@login_required
def records_block(request, org_id):
    """Render the compliance records table for an org (HTMX block)."""
    org, acting = _require_member(request, org_id)
    if not org:
        return HttpResponseForbidden("You are not a member of this org.")
    records = ComplianceRecord.objects.filter(org=org).order_by("-last_updated", "-id")
    return render(
        request,
        "ui/partials/_records.html",
        {"org": org, "records": records, "actor": acting},
    )

@login_required
def record_row(request, org_id, pk):
    """Render a single table row (used after inline edits)."""
    org, acting = _require_member(request, org_id)
    if not org:
        return HttpResponseForbidden("You are not a member of this org.")
    r = get_object_or_404(ComplianceRecord, id=pk, org=org)
    return render(request, "ui/partials/_record_row.html", {"org": org, "r": r, "actor": acting})

# ---- Actions (HTMX) --------------------------------------------------------

@require_POST
@login_required
def record_create(request, org_id):
    org, acting = _require_member(request, org_id)
    if not org:
        return HttpResponseForbidden("You are not a member of this org.")

    # owners/admins can create (adjust if you want members too)
    if acting.role not in (Membership.OWNER, Membership.ADMIN):
        return HttpResponseForbidden("Admin or Owner required.")

    requirement = (request.POST.get("requirement") or "").strip()
    status_val = (request.POST.get("status") or "").strip()  # falls back to model default if blank
    if not requirement:
        # Re-render block with an inline error? For now, keep it simple.
        records = ComplianceRecord.objects.filter(org=org).order_by("-last_updated", "-id")
        return render(request, "ui/partials/_records.html",
                      {"org": org, "records": records, "actor": acting, "error": "Requirement is required."},
                     )

    r = ComplianceRecord(org=org, requirement=requirement)
    if status_val:
        r.status = status_val
    r.save()

    # Return the whole block so totals/empty-state etc. update reliably
    return records_block(request, org_id)

@require_http_methods(["GET", "POST"])
@login_required
def record_edit(request, org_id, pk):
    org, acting = _require_member(request, org_id)
    if not org:
        return HttpResponseForbidden("You are not a member of this org.")

    if acting.role not in (Membership.OWNER, Membership.ADMIN):
        return HttpResponseForbidden("Admin or Owner required.")

    r = get_object_or_404(ComplianceRecord, id=pk, org=org)

    if request.method == "GET":
        # If you have a dedicated edit partial, render it here; otherwise return row.
        return render(request, "ui/partials/_record_row.html", {"org": org, "r": r, "actor": acting})

    # POST: update minimal fields
    new_req = (request.POST.get("requirement") or "").strip()
    new_status = (request.POST.get("status") or "").strip()

    if new_req:
        r.requirement = new_req
    if new_status:
        r.status = new_status
    r.save()

    # Return just the updated row (common HTMX pattern)
    return record_row(request, org_id, pk)

@require_POST
@login_required
def record_delete(request, org_id, pk):
    org, acting = _require_member(request, org_id)
    if not org:
        return HttpResponseForbidden("You are not a member of this org.")

    if acting.role not in (Membership.OWNER, Membership.ADMIN):
        return HttpResponseForbidden("Admin or Owner required.")

    r = get_object_or_404(ComplianceRecord, id=pk, org=org)
    r.delete()

    # Re-render the whole block so empty-state or paging updates correctly
    return records_block(request, org_id)


@login_required
def records_block(request, org_id):
    """HTMX: render the compliance records table for an org."""
    org = get_object_or_404(Org, id=org_id)
    if not _is_member(request.user, org):
        return HttpResponseForbidden("You don't have access to this organisation.")
    return _render_records_block(request, org)


@require_POST
@login_required
def record_create(request, org_id):
    """HTMX: create a record then re-render the block."""
    org = get_object_or_404(Org, id=org_id)
    if not _is_admin(request.user, org):
        return HttpResponseForbidden("Admin or Owner role required.")

    requirement = (request.POST.get("requirement") or "").strip()
    status = (request.POST.get("status") or "").strip()

    if not requirement:
        return _render_records_block(request, org, error="Requirement is required.")
    if status and status not in _valid_statuses():
        return _render_records_block(request, org, error="Invalid status.")

    ComplianceRecord.objects.create(org=org, requirement=requirement, status=status or None)
    return _render_records_block(request, org, ok=True)


@require_http_methods(["POST", "PATCH"])
@login_required
def record_edit(request, org_id, pk):
    """HTMX: update a record then re-render the block."""
    org = get_object_or_404(Org, id=org_id)
    if not _is_admin(request.user, org):
        return HttpResponseForbidden("Admin or Owner role required.")

    rec = get_object_or_404(ComplianceRecord, id=pk, org=org)

    requirement = request.POST.get("requirement")
    status = request.POST.get("status")

    if requirement is not None:
        requirement = requirement.strip()
        if not requirement:
            return _render_records_block(request, org, error="Requirement cannot be empty.")
        rec.requirement = requirement

    if status is not None:
        status = status.strip()
        if status and status not in _valid_statuses():
            return _render_records_block(request, org, error="Invalid status.")
        rec.status = status or rec.status

    rec.save()
    return _render_records_block(request, org, ok=True)


@require_POST
@login_required
def record_delete(request, org_id, pk):
    """HTMX: delete a record then re-render the block."""
    org = get_object_or_404(Org, id=org_id)
    if not _is_admin(request.user, org):
        return HttpResponseForbidden("Admin or Owner role required.")

    rec = get_object_or_404(ComplianceRecord, id=pk, org=org)
    rec.delete()
    return _render_records_block(request, org, ok=True)
