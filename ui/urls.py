from django.urls import path
from . import views

app_name = "ui"

urlpatterns = [

    path("", views.home, name="home"),
    # Org detail page (this fixes /orgs/3/ 404)
    path("orgs/<int:org_id>/", views.org_detail, name="org-detail"),

    # Org name inline
    path("orgs/<int:org_id>/name/", views.org_name_partial, name="org-name")
    ,
    path("orgs/<int:org_id>/name/edit/", views.org_name_edit, name="org-name-edit"),

    # Members panel + role management
    path("orgs/<int:org_id>/members/", views.org_members_partial, name="org-members"),
    path("orgs/<int:org_id>/invitations/create/", views.org_invite_create, name="org-invite-create"),
    path("orgs/<int:org_id>/members/<int:member_id>/update/", views.org_member_update, name="org-member-update"),
    path("orgs/<int:org_id>/members/<int:member_id>/toggle/", views.org_member_toggle, name="org-member-toggle"),

    # Records (inline rows / edit / delete / create)
    path("records/<int:pk>/", views.record_row, name="record-row"),
    path("records/<int:pk>/edit/", views.record_edit, name="record-edit"),
    path("records/<int:pk>/delete/", views.record_delete, name="record-delete"),
    path("orgs/<int:org_id>/records/create/", views.record_create, name="record-create"),
]
