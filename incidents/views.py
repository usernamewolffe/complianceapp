# incidents/views.py
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_http_methods, require_POST
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .models import Incident, IncidentUpdate, IncidentAttachment
from orgs.models import Org, Membership


# --- helpers ---------------------------------------------------------------

def _actor_member(request, org_id):
    return Membership.objects.filter(
        org_id=org_id, user=request.user, is_active=True
    ).first()

def _require_member(request, org_id):
    actor = _actor_member(request, org_id)
    if not actor:
        return None, HttpResponseForbidden("You are not a member of this org.")
    return actor, None

def _require_admin(request, org_id):
    actor, err = _require_member(request, org_id)
    if err:
        return None, err
    if actor.role not in (Membership.OWNER, Membership.ADMIN):
        return None, HttpResponseForbidden("Admin or Owner required.")
    return actor, None


# --- blocks / pages --------------------------------------------------------

@login_required
def incidents_block(request, org_id):
    """
    Render the incidents table for an org (used by HTMX on the org page).
    Supplies classifications/severities for the quick-create form.
    """
    actor, err = _require_member(request, org_id)
    if err:
        return err

    org = get_object_or_404(Org, id=org_id)
    incidents = (
        Incident.objects.filter(org=org)
        .select_related("owner")
        .order_by("-aware_at", "-created_at")
    )

    return render(
        request,
        "ui/partials/_incidents.html",
        {
            "org": org,
            "incidents": incidents,
            "actor": actor,
            "classifications": Incident.Classification.choices,
            "severities": Incident.Severity.choices,
            "ok": request.GET.get("ok") == "1",
        },
    )

@login_required
def incident_detail(request, org_id, incident_id):
    actor, err = _require_member(request, org_id)
    if err:
        return err
    org = get_object_or_404(Org, id=org_id)
    incident = get_object_or_404(Incident, id=incident_id, org=org)
    updates = incident.updates.select_related("created_by").all()
    attachments = incident.attachments.select_related("uploaded_by").all()
    return render(
        request,
        "ui/incident_detail.html",
        {
            "org": org,
            "incident": incident,
            "updates": updates,
            "attachments": attachments,
            "actor": actor,
            "statuses": Incident.Status.choices,
        },
    )


# --- actions (HTMX) --------------------------------------------------------

@login_required
@require_http_methods(["POST"])
def incident_create(request, org_id):
    """
    Create a new incident, then re-render the same block (HTMX).
    Any active member can create; tighten to admin/owner by switching to _require_admin.
    """
    actor, err = _require_member(request, org_id)
    if err:
        return err

    org = get_object_or_404(Org, id=org_id)

    title = (request.POST.get("title") or "").strip()
    classification = request.POST.get("classification") or Incident.Classification.OTHER
    severity = request.POST.get("severity") or Incident.Severity.MEDIUM
    aware_at_raw = request.POST.get("aware_at") or ""
    description = (request.POST.get("description") or "").strip()

    if not title:
        return JsonResponse({"error": "Title is required."}, status=400)

    valid_class = {c for c, _ in Incident.Classification.choices}
    valid_sev = {s for s, _ in Incident.Severity.choices}
    if classification not in valid_class:
        return JsonResponse({"error": "Invalid classification."}, status=400)
    if severity not in valid_sev:
        return JsonResponse({"error": "Invalid severity."}, status=400)

    aware_at = None
    if aware_at_raw:
        # parse <input type="datetime-local"> string
        aware_at = parse_datetime(aware_at_raw)
        if aware_at and timezone.is_naive(aware_at):
            aware_at = timezone.make_aware(aware_at, timezone.get_current_timezone())
    if not aware_at:
        aware_at = timezone.now()

    Incident.objects.create(
        org=org,
        title=title,
        classification=classification,
        severity=severity,
        aware_at=aware_at,
        status=Incident.Status.OPEN,
        owner=request.user,
        description=description,
    )

    # Re-render the block with success banner
    incidents = (
        Incident.objects.filter(org=org)
        .select_related("owner")
        .order_by("-aware_at", "-created_at")
    )
    return render(
        request,
        "ui/partials/_incidents.html",
        {
            "org": org,
            "incidents": incidents,
            "actor": actor,
            "classifications": Incident.Classification.choices,
            "severities": Incident.Severity.choices,
            "ok": True,
        },
    )

@login_required
@require_http_methods(["POST"])
def incident_status_update(request, org_id, incident_id):
    actor, err = _require_admin(request, org_id)
    if err:
        return err
    org = get_object_or_404(Org, id=org_id)
    incident = get_object_or_404(Incident, id=incident_id, org=org)

    new_status = request.POST.get("status", "")
    valid = {c for c, _ in Incident.Status.choices}
    if new_status not in valid:
        return JsonResponse({"error": "Invalid status."}, status=400)

    incident.status = new_status
    incident.updated_at = timezone.now()
    incident.save(update_fields=["status", "updated_at"])

    # re-render the single row
    return render(
        request,
        "ui/partials/_incident_row.html",
        {"org": org, "i": incident, "actor": actor},
    )

@login_required
@require_POST
def incident_note_add(request, org_id, incident_id):
    actor, err = _require_member(request, org_id)
    if err:
        return err
    org = get_object_or_404(Org, id=org_id)
    incident = get_object_or_404(Incident, id=incident_id, org=org)

    note = (request.POST.get("note") or "").strip()
    if not note:
        return JsonResponse({"error": "Note cannot be empty."}, status=400)

    IncidentUpdate.objects.create(
        incident=incident, note=note, created_by=request.user
    )
    updates = incident.updates.select_related("created_by").all()
    return render(
        request,
        "ui/partials/_incident_updates.html",
        {"incident": incident, "updates": updates},
    )

@login_required
@require_POST
def incident_attachment_add(request, org_id, incident_id):
    actor, err = _require_member(request, org_id)
    if err:
        return err
    org = get_object_or_404(Org, id=org_id)
    incident = get_object_or_404(Incident, id=incident_id, org=org)

    f = request.FILES.get("file")
    if not f:
        return JsonResponse({"error": "No file uploaded."}, status=400)

    IncidentAttachment.objects.create(
        incident=incident,
        file=f,
        uploaded_by=request.user,
    )
    attachments = incident.attachments.select_related("uploaded_by").all()
    return render(
        request,
        "ui/partials/_incident_attachments.html",
        {"incident": incident, "attachments": attachments},
    )
