# incidents/urls.py
from django.urls import path
from . import views

app_name = "incidents"

urlpatterns = [
    # ------------------------------------------------------------------
    # Site-scoped list + create
    # ------------------------------------------------------------------
    path(
        "orgs/<int:org_id>/sites/<int:site_id>/incidents/",
        views.site_incidents_block,
        name="site-incidents-block",
    ),
    path(
        "orgs/<int:org_id>/sites/<int:site_id>/incidents/create/",
        views.incident_create,
        name="incident-create",
    ),

    # ------------------------------------------------------------------
    # Obligation actions (per-authority pills)
    # ------------------------------------------------------------------
    path(
        "orgs/<int:org_id>/sites/<int:site_id>/incidents/<int:incident_id>/obligations/<int:obligation_id>/file/",
        views.obligation_file,
        name="obligation-file",
    ),
    path(
        "orgs/<int:org_id>/sites/<int:site_id>/incidents/<int:incident_id>/seed-obligations/",
        views.seed_obligations,
        name="seed-obligations",
    ),

    # ------------------------------------------------------------------
    # Inline title edit (org-scoped reverse is enough)
    # ------------------------------------------------------------------
    path(
        "orgs/<int:org_id>/incidents/<int:incident_id>/title/form/",
        views.incident_title_form,
        name="title-form",
    ),

    # ------------------------------------------------------------------
    # "Report filed" flow (org-scoped; templates reverse these names)
    # ------------------------------------------------------------------
    path(
        "orgs/<int:org_id>/incidents/<int:incident_id>/file/form/",
        views.incident_file_form,
        name="incident-file-form",
    ),
    path(
        "orgs/<int:org_id>/incidents/<int:incident_id>/file/submit/",
        views.incident_file_submit,
        name="incident-file-submit",
    ),

    # ------------------------------------------------------------------
    # Notes & Files blocks + actions (org-scoped)
    # ------------------------------------------------------------------
    path(
        "orgs/<int:org_id>/incidents/<int:incident_id>/notes/",
        views.incident_notes_block,
        name="notes-block",
    ),
    path(
        "orgs/<int:org_id>/incidents/<int:incident_id>/notes/create/",
        views.incident_note_create,
        name="note-create",
    ),
    path(
        "orgs/<int:org_id>/incidents/<int:incident_id>/files/",
        views.incident_files_block,
        name="files-block",
    ),
    path(
        "orgs/<int:org_id>/incidents/<int:incident_id>/files/upload/",
        views.incident_file_upload,
        name="file-upload",
    ),
    path(
        "orgs/<int:org_id>/incidents/<int:incident_id>/files/<int:attachment_id>/delete/",
        views.incident_file_delete,
        name="file-delete",
    ),

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------
    path(
        "orgs/<int:org_id>/incidents/<int:incident_id>/export/",
        views.incident_export,
        name="incident-export",
    ),
    path(
        "orgs/<int:org_id>/incidents/<int:incident_id>/export/annex-e.json",
        views.incident_export_annex_e_json,
        name="incident-export-annex-e-json",
    ),
    path(
        "orgs/<int:org_id>/incidents/<int:incident_id>/export/annex-e.html",
        views.incident_export_annex_e_html,
        name="incident-export-annex-e-html",
    ),

    # ------------------------------------------------------------------
    # Legacy org-scoped list (incidents without a site)
    # ------------------------------------------------------------------
    path(
        "orgs/<int:org_id>/incidents/",
        views.org_incidents_block,
        name="org-incidents-block",
    ),
]
