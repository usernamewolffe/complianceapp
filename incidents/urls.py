# incidents/urls.py
from django.urls import path
from . import views

app_name = "incidents"

urlpatterns = [
    path("", views.incidents_block, name="incidents-block"),          # GET (HTMX load)
    path("create/", views.incident_create, name="incident-create"),   # POST (HTMX)
    path("<int:incident_id>/", views.incident_detail, name="detail"),
    path("<int:incident_id>/status/", views.incident_status_update, name="status-update"),
    path("<int:incident_id>/notes/add/", views.incident_note_add, name="note-add"),
    path("<int:incident_id>/attachments/add/", views.incident_attachment_add, name="attachment-add"),
]
