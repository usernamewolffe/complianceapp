# compliance_app/urls.py
from django.urls import path
from . import views

app_name = "compliance_ui"  # must match the namespace used in config/urls.py

urlpatterns = [
    path("", views.records_block, name="org-records-block"),                 # GET (HTMX load)
    path("create/", views.record_create, name="record-create"),              # POST
    path("<int:pk>/", views.record_row, name="record-row"),                  # GET (row refresh)
    path("<int:pk>/edit/", views.record_edit, name="record-edit"),           # GET/POST
    path("<int:pk>/delete/", views.record_delete, name="record-delete"),     # POST
]
