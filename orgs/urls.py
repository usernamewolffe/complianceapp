from django.urls import path
from orgs import views

urlpatterns = [
    # UI page
    path("orgs/<int:org_id>/members/", views.org_members_page, name="org-members-ui"),
    # members block (HTMX partial)  <<< add this
    path("orgs/<int:org_id>/members/block/", views.org_members_block, name="org-members-block"),

    # Members actions
    path("orgs/<int:org_id>/members/<int:member_id>", views.org_member_update, name="org_member_update"),
    path("orgs/<int:org_id>/members/<int:member_id>/toggle", views.org_member_toggle, name="org_member_toggle"),
    path("orgs/<int:org_id>/members/<int:member_id>", views.org_member_update, name="org-member-update"),
    path("orgs/<int:org_id>/members/<int:member_id>/toggle", views.org_member_toggle, name="org-member-toggle"),

    # Invitations
    path("orgs/<int:org_id>/invitations/create", views.org_invite_create, name="org-invite-create"),  # <-- add this
    path("orgs/<int:org_id>/invitations/<int:inv_id>/cancel", views.invitation_cancel, name="invitation_cancel"),
    path("orgs/<int:org_id>/invitations/<int:inv_id>/resend", views.invitation_resend, name="invitation_resend"),
]
