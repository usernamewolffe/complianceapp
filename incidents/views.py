# incidents/views.py
from datetime import timedelta
import json
import logging

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q, F
from django.http import (
    Http404,
    HttpResponse,
    HttpResponseBadRequest,
    HttpResponseForbidden,
    JsonResponse,
)
from django.shortcuts import get_object_or_404, render
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.text import slugify
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from orgs.models import Org, Membership, Site

from .models import (
    Incident,
    Obligation,
    IncidentNote,
    IncidentAttachment,
    create_default_obligations,
)
from .annex_e import incident_to_annex_e

log = logging.getLogger(__name__)


# --------------------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------------------

def _reported_hm(aware_at, reported_at):
    """
    Return 'Hh MMm' between aware_at and reported_at (never negative).
    Used by the export to display duration.
    """
    if not aware_at or not reported_at:
        return None
    delta = reported_at - aware_at
    total_minutes = max(0, int(delta.total_seconds() // 60))
    h, m = divmod(total_minutes, 60)
    return f"{h}h {m:02d}m"


def _require_member(request, org: Org) -> bool:
    """User must be an active member of the org."""
    return Membership.objects.filter(org=org, user=request.user, is_active=True).exists()


def _incident_for_org_or_404(org_id: int, incident_id: int) -> Incident:
    """
    Fetch incident and ensure it belongs to the given org — either via org FK (legacy)
    or via site->org relationship.
    """
    inc = (
        Incident.objects.select_related("site")
        .filter(Q(id=incident_id), Q(org_id=org_id) | Q(site__org_id=org_id))
        .first()
    )
    if not inc:
        raise Http404("Incident not found for this organisation.")
    return inc


def _serialize_for_list(inc: Incident):
    """
    Attach client-only 'notification_deadline' used by any countdown UI in the table.
    Only set when not yet reported and we have an aware_at.
    """
    if getattr(inc, "status", None) != "reported" and getattr(inc, "aware_at", None):
        inc.notification_deadline = inc.aware_at + timedelta(hours=72)
    else:
        inc.notification_deadline = None
    return {"obj": inc}


def _render_site_block(request, org: Org, site: Site):
    container_id = (
        request.GET.get("container_id")
        or request.POST.get("container_id")
        or f"site-{site.id}-incidents"
    )
    items = [
        _serialize_for_list(i)
        for i in Incident.objects.filter(site=site).order_by("-id")
    ]
    return render(
        request,
        "ui/partials/_incidents.html",
        {"org": org, "site": site, "incidents": items, "container_id": container_id},
    )


def _render_org_block(request, org: Org):
    # Legacy fallback: incidents with no site
    items = [
        _serialize_for_list(i)
        for i in Incident.objects.filter(org=org, site__isnull=True).order_by("-id")
    ]
    return render(
        request,
        "ui/partials/_incidents.html",
        {"org": org, "incidents": items, "container_id": "incidents-block"},
    )


# --------------------------------------------------------------------------------------
# Site-scoped incidents list & create
# --------------------------------------------------------------------------------------

@require_http_methods(["GET"])
def site_incidents_block(request, org_id, site_id):
    # Honor the container id your _sites.html passes via hx-vals
    container_id = (
        request.GET.get("container_id")
        or request.POST.get("container_id")
        or f"site-{site_id}-incidents"
    )
    incidents = (
        Incident.objects.filter(org_id=org_id, site_id=site_id)
        .order_by(F("aware_at").desc(nulls_last=True), "-created_at")
    )
    return render(
        request,
        "ui/partials/_site_incidents_block.html",
        {
            "org_id": org_id,
            "site_id": site_id,
            "incidents": incidents,
            "container_id": container_id,
        },
    )


@require_http_methods(["GET", "POST"])
def incident_create(request, org_id, site_id):
    if request.method == "GET":
        container_id = (
            request.GET.get("container_id")
            or request.POST.get("container_id")
            or f"site-{site_id}-incidents"
        )
        return render(
            request,
            "ui/partials/_incident_create_form.html",
            {"org_id": org_id, "site_id": site_id, "container_id": container_id},
        )

    # POST
    title = (request.POST.get("title") or "").strip()
    severity = (request.POST.get("severity") or "moderate").strip()
    container_id = request.POST.get("container_id") or f"site-{site_id}-incidents"
    if not title:
        return HttpResponseBadRequest("Title required")

    inc = Incident.objects.create(
        org_id=org_id,  # kept for legacy; ok if nullable during transition
        site_id=site_id,
        title=title,
        severity=severity,
        aware_at=timezone.now(),
    )
    # Seed default obligations so the timer cell immediately shows pills
    create_default_obligations(inc)

    incidents = (
        Incident.objects.filter(org_id=org_id, site_id=site_id)
        .order_by(F("aware_at").desc(nulls_last=True), "-created_at")
    )
    return render(
        request,
        "ui/partials/_site_incidents_block.html",
        {
            "org_id": org_id,
            "site_id": site_id,
            "incidents": incidents,
            "container_id": container_id,
        },
    )


# --------------------------------------------------------------------------------------
# Obligation actions (per-authority pills)
# --------------------------------------------------------------------------------------

@require_POST
def obligation_file(request, org_id, site_id, incident_id, obligation_id):
    """
    Marks a single obligation as filed (and optionally saves a submission ref).
    Returns just the pill partial so HTMX swaps it in-place.
    """
    ob = get_object_or_404(
        Obligation,
        id=obligation_id,
        incident_id=incident_id,
        incident__org_id=org_id,
        incident__site_id=site_id,
    )
    ob.submission_ref = (request.POST.get("submission_ref") or ob.submission_ref or "").strip()
    if not ob.filed_at:
        ob.filed_at = timezone.now()
        ob.save(update_fields=["submission_ref", "filed_at"])
    else:
        ob.save(update_fields=["submission_ref"])

    return render(
        request,
        "ui/partials/_obligation_cell.html",
        {"ob": ob, "org_id": org_id, "site_id": site_id, "incident_id": incident_id},
    )


@require_POST
def seed_obligations(request, org_id, site_id, incident_id):
    """
    Creates default obligations (Ofgem/ICO 72h) for an incident that has none yet.
    Returns the timer cell so HTMX swaps it in-place.
    """
    inc = get_object_or_404(
        Incident, id=incident_id, org_id=org_id, site_id=site_id
    )
    create_default_obligations(inc)
    return render(
        request,
        "ui/partials/timer_cell.html",
        {"incident": inc, "org_id": org_id, "site_id": site_id},
    )


# --------------------------------------------------------------------------------------
# Inline title edit (single cell swap)
# --------------------------------------------------------------------------------------

@login_required
@require_http_methods(["GET", "POST"])
def incident_title_form(request, org_id, incident_id, site_id=None):
    """
    GET (no params): show edit form  -> _incident_title_form.html
    GET ?cancel=1:  restore display  -> _title_cell.html
    POST:           save + display   -> _title_cell.html
    """
    org = get_object_or_404(Org, pk=org_id)
    if not _require_member(request, org):
        return HttpResponseForbidden("You don't have access to this organisation.")
    inc = _incident_for_org_or_404(org_id, incident_id)

    dom_prefix = (
        request.GET.get("dom_prefix")
        or request.POST.get("dom_prefix")
        or request.GET.get("container_id")
        or "incidents-block"
    )

    # Cancel -> restore the title display cell (which includes Notes/Files buttons)
    if request.method == "GET" and request.GET.get("cancel"):
        return render(
            request,
            "ui/partials/_title_cell.html",
            {"org_id": org_id, "inc": inc, "dom_prefix": dom_prefix},
        )

    if request.method == "POST":
        title = (request.POST.get("title") or "").strip()
        if not title:
            return render(
                request,
                "ui/partials/_incident_title_form.html",
                {"org_id": org_id, "inc": inc, "dom_prefix": dom_prefix, "error": "Title is required."},
                status=400,
            )
        inc.title = title
        inc.save(update_fields=["title"])
        return render(
            request,
            "ui/partials/_title_cell.html",
            {"org_id": org_id, "inc": inc, "dom_prefix": dom_prefix},
        )

    # GET -> edit form
    return render(
        request,
        "ui/partials/_incident_title_form.html",
        {"org_id": org_id, "inc": inc, "dom_prefix": dom_prefix},
    )


# --------------------------------------------------------------------------------------
# "Report Submitted" inline flow (legacy single-clock flow, kept for compat)
# --------------------------------------------------------------------------------------

@login_required
@require_POST
def incident_file_submit(request, org_id, incident_id):
    """
    Marks an incident as reported and returns:
      - the updated status cell (normal swap)
      - the updated timer cell (out-of-band swap)
    """
    log.info(
        "POST /file/submit org=%s incident=%s HX=%s",
        org_id,
        incident_id,
        request.headers.get("HX-Request"),
    )

    if not org_id or not incident_id:
        return HttpResponseBadRequest("Missing IDs")

    with transaction.atomic():
        inc = _incident_for_org_or_404(org_id, incident_id)

        # Normalise inputs
        notes = (request.POST.get("report_notes") or inc.report_notes or "").strip()
        inc.report_notes = notes

        if "report_reference" in request.POST:
            inc.report_reference = (request.POST.get("report_reference") or "").strip()

        # Mark as reported (idempotent)
        if inc.reported_at is None:
            inc.reported_at = timezone.now()
        inc.status = Incident.Status.REPORTED

        inc.save(update_fields=["report_notes", "report_reference", "reported_at", "status"])

    # If HTMX, return the two partials. Keep your existing OOB template name.
    if request.headers.get("HX-Request"):
        dom_prefix = request.POST.get("dom_prefix") or "incidents-block"  # fallback
        status_html = render_to_string(
            "ui/partials/_status_cell.html",
            {"incident": inc, "org_id": org_id, "dom_prefix": dom_prefix},
            request=request,
        )
        timer_html = render_to_string(
            "ui/partials/_timer_cell_oob.html",  # your existing OOB wrapper template
            {"incident": inc, "dom_prefix": dom_prefix},
            request=request,
        )
        return HttpResponse(status_html + timer_html)

    # Non-HTMX fallback: just render a minimal confirmation (rare path)
    return HttpResponse("Reported")


@login_required
@require_GET
def incident_file_form(request, org_id, incident_id, site_id=None):
    """
    Optional GET-only view for a 'Report submitted' inline form.
    If ?cancel=1 is passed it renders the normal status cell again.
    """
    org = get_object_or_404(Org, pk=org_id)
    if not _require_member(request, org):
        return HttpResponseForbidden("You don't have access to this organisation.")
    inc = _incident_for_org_or_404(org_id, incident_id)

    dom_prefix = (
        request.GET.get("dom_prefix")
        or request.GET.get("container_id")
        or "incidents-block"
    )

    # Cancel -> swap back to normal status cell
    if request.GET.get("cancel"):
        return render(
            request,
            "ui/partials/_status_cell.html",
            {"incident": inc, "org_id": org_id, "dom_prefix": dom_prefix},
        )

    # Otherwise render a simple file form (if you still use it)
    return render(
        request,
        "ui/partials/_file_form.html",
        {"org": org, "org_id": org_id, "inc": inc, "dom_prefix": dom_prefix},
    )


# --------------------------------------------------------------------------------------
# Notes & Files (blocks + create/upload/delete)
# --------------------------------------------------------------------------------------

def _notes_ctx(org, inc):
    notes = inc.notes.select_related("created_by").order_by("id")
    return {"org": org, "inc": inc, "notes": notes}

def _files_ctx(org, inc):
    files = inc.attachments.select_related("uploaded_by").order_by("id")
    return {"org": org, "inc": inc, "files": files}

@login_required
@require_GET
def incident_notes_block(request, org_id, incident_id, site_id=None):
    org = get_object_or_404(Org, pk=org_id)
    if not _require_member(request, org):
        return HttpResponseForbidden("You don't have access to this organisation.")
    inc = _incident_for_org_or_404(org_id, incident_id)
    return render(request, "ui/partials/_incident_notes.html", _notes_ctx(org, inc))

@login_required
@require_POST
def incident_note_create(request, org_id, incident_id, site_id=None):
    org = get_object_or_404(Org, pk=org_id)
    if not _require_member(request, org):
        return HttpResponseForbidden("You don't have access to this organisation.")
    inc = _incident_for_org_or_404(org_id, incident_id)

    body = (request.POST.get("body") or "").strip()
    if body:
        IncidentNote.objects.create(
            incident=inc, body=body, created_by=getattr(request, "user", None)
        )
    return render(request, "ui/partials/_incident_notes.html", _notes_ctx(org, inc))

@login_required
@require_GET
def incident_files_block(request, org_id, incident_id, site_id=None):
    org = get_object_or_404(Org, pk=org_id)
    if not _require_member(request, org):
        return HttpResponseForbidden("You don't have access to this organisation.")
    inc = _incident_for_org_or_404(org_id, incident_id)
    return render(request, "ui/partials/_incident_files.html", _files_ctx(org, inc))

@login_required
@require_POST
def incident_file_upload(request, org_id, incident_id, site_id=None):
    org = get_object_or_404(Org, pk=org_id)
    if not _require_member(request, org):
        return HttpResponseForbidden("You don't have access to this organisation.")
    inc = _incident_for_org_or_404(org_id, incident_id)

    f = request.FILES.get("file")
    label = (request.POST.get("label") or "").strip()
    if f:
        IncidentAttachment.objects.create(
            incident=inc, file=f, label=label, uploaded_by=getattr(request, "user", None)
        )
    return render(request, "ui/partials/_incident_files.html", _files_ctx(org, inc))

@login_required
@require_POST
def incident_file_delete(request, org_id, incident_id, attachment_id, site_id=None):
    org = get_object_or_404(Org, pk=org_id)
    if not _require_member(request, org):
        return HttpResponseForbidden("You don't have access to this organisation.")
    inc = _incident_for_org_or_404(org_id, incident_id)
    att = get_object_or_404(IncidentAttachment, pk=attachment_id, incident=inc)
    att.delete()
    return render(request, "ui/partials/_incident_files.html", _files_ctx(org, inc))


# --------------------------------------------------------------------------------------
# Export (HTML download)
# --------------------------------------------------------------------------------------

@login_required
@require_GET
def incident_export(request, org_id, incident_id, site_id=None):
    """
    Download a self-contained HTML export for an incident.
    Template: ui/exports/incident_export.html
    """
    org = get_object_or_404(Org, pk=org_id)
    if not _require_member(request, org):
        return HttpResponseForbidden("You don't have access to this organisation.")
    inc = _incident_for_org_or_404(org_id, incident_id)

    aware_at = getattr(inc, "aware_at", None)
    deadline_at = (
        aware_at + timedelta(hours=72)
        if getattr(inc, "status", None) != "reported" and aware_at
        else None
    )
    reported_hm = (
        _reported_hm(aware_at, getattr(inc, "reported_at", None))
        if getattr(inc, "status", None) == "reported"
        else None
    )

    ctx = {"org": org, "inc": inc, "deadline_at": deadline_at, "reported_hm": reported_hm}

    base = slugify((getattr(inc, "title", "") or "incident"))
    when_src = getattr(inc, "created_at", None) or aware_at or timezone.now()
    when = timezone.localtime(when_src).strftime("%Y-%m-%d")
    filename = f"{base or 'incident'}-{when}.html"

    resp = render(request, "ui/exports/incident_export.html", ctx)
    resp["Content-Disposition"] = f'attachment; filename="{filename}"'
    return resp


# --------------------------------------------------------------------------------------
# Legacy org-scoped list (incidents with no site)
# --------------------------------------------------------------------------------------

@login_required
@require_GET
def org_incidents_block(request, org_id):
    """Legacy list for incidents without a site (kept for backwards compat)."""
    org = get_object_or_404(Org, pk=org_id)
    if not _require_member(request, org):
        return HttpResponseForbidden("You don't have access to this organisation.")
    return _render_org_block(request, org)


# --------------------------------------------------------------------------------------
# Annex E exports (JSON + HTML)
# --------------------------------------------------------------------------------------

@login_required
@require_GET
def incident_export_annex_e_json(request, org_id, incident_id, site_id=None):
    org = get_object_or_404(Org, pk=org_id)
    if not _require_member(request, org):
        return HttpResponseForbidden("You don't have access to this organisation.")
    inc = _incident_for_org_or_404(org_id, incident_id)

    reporter_name = getattr(request.user, "get_full_name", lambda: "")() or request.user.username
    reporter_email = getattr(request.user, "email", "") or ""

    payload = incident_to_annex_e(
        inc,
        reporter_name=reporter_name,
        reporter_email=reporter_email,
        reporter_role="",
        reporter_phone="",
        essential_service="",  # TODO: collect/store per site/org
        status="detected",     # TODO: collect from a form field
        stage="ongoing",       # TODO: collect from a form field
    )

    resp = HttpResponse(
        json.dumps(payload, indent=2),
        content_type="application/json",
    )
    filename = f"annex-e-incident-{inc.id}.json"
    resp["Content-Disposition"] = f'attachment; filename="{filename}"'
    return resp


@login_required
@require_GET
def incident_export_annex_e_html(request, org_id, incident_id, site_id=None):
    org = get_object_or_404(Org, pk=org_id)
    if not _require_member(request, org):
        return HttpResponseForbidden("You don't have access to this organisation.")
    inc = _incident_for_org_or_404(org_id, incident_id)

    reporter_name = getattr(request.user, "get_full_name", lambda: "")() or request.user.username
    reporter_email = getattr(request.user, "email", "") or ""

    data = incident_to_annex_e(
        inc,
        reporter_name=reporter_name,
        reporter_email=reporter_email,
        status="detected",        # TODO: wire from UI field
        stage="ongoing",          # TODO: wire from UI field
        essential_service="",     # TODO: store on site/org and map here
    )

    resp = render(request, "ui/exports/annex_e.html", {"org": org, "inc": inc, "data": data})
    base = f"annex-e-incident-{inc.id}"

    # ?as=word gives a .doc (Word opens HTML nicely)
    if request.GET.get("as") in {"word", "doc"}:
        resp["Content-Type"] = "application/msword"
        resp["Content-Disposition"] = f'attachment; filename="{base}.doc"'
    else:
        resp["Content-Disposition"] = f'attachment; filename="{base}.html"'
    return resp
