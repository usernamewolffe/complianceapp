# orgs/urls.py
from django.urls import path
from . import views

app_name = "orgs"

urlpatterns = [
    # Members UI + block
    path("orgs/<int:org_id>/members/", views.org_members_page, name="org-members-ui"),
    path("orgs/<int:org_id>/members/block/", views.org_members_block, name="org-members-block"),

    # Member actions (names match _members.html)
    path("orgs/<int:org_id>/members/<int:member_id>/update/", views.org_member_update, name="org-member-update"),
    path("orgs/<int:org_id>/members/<int:member_id>/toggle/", views.org_member_toggle, name="org-member-toggle"),

    # Invitations (names match _members.html)
    path("orgs/<int:org_id>/invitations/create/", views.org_invite_create, name="org-invite-create"),
    path("orgs/<int:org_id>/invitations/<int:inv_id>/cancel/", views.invitation_cancel, name="invitation-cancel"),
    path("orgs/<int:org_id>/invitations/<int:inv_id>/resend/", views.invitation_resend, name="invitation-resend"),

    # Sites block + actions
    path("orgs/<int:org_id>/sites/block/", views.org_sites_block, name="org-sites-block"),
    path("orgs/<int:org_id>/sites/create/", views.site_create, name="site-create"),
    path("orgs/<int:org_id>/sites/<int:site_id>/delete/", views.site_delete, name="site-delete"),
    path("orgs/<int:org_id>/sites/<int:site_id>/edit/", views.site_edit, name="site-edit"),

    path("orgs/<int:org_id>/sites/<int:site_id>/delete/", views.site_delete, name="site-delete",)
]
