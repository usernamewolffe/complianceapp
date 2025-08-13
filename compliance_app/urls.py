# compliance_app/urls.py
from django.urls import path
from . import views

app_name = "compliance_ui"

urlpatterns = [
    # HTMX block loader (requires org_id from the parent include)
    path("", views.records_block, name="org-records-block"),

    # Inline actions for the table/form
    path("create/", views.record_create, name="record-create"),
    path("<int:pk>/edit/", views.record_edit, name="record-edit"),
    path("<int:pk>/delete/", views.record_delete, name="record-delete"),
]
