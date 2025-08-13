from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from django.contrib.auth import get_user_model

from orgs.models import Org, Membership, OrgInvite
from orgs.logic.guards import guard_role_change, guard_toggle_active, GuardError

User = get_user_model()

class BaseSetup(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="owner", password="x", email="o@example.com")
        self.alice = User.objects.create_user(username="alice", password="x", email="a@example.com")
        self.bob   = User.objects.create_user(username="bob",   password="x", email="b@example.com")

        self.org = Org.objects.create(user=self.owner, name="Test Org")  # creator field exists in your model
        self.m_owner = Membership.objects.create(org=self.org, user=self.owner, role="owner", is_active=True, accepted_at=timezone.now())
        self.m_alice = Membership.objects.create(org=self.org, user=self.alice, role="member", is_active=True, accepted_at=timezone.now())
        self.m_bob   = Membership.objects.create(org=self.org, user=self.bob,   role="admin",  is_active=True, accepted_at=timezone.now())

class GuardTests(BaseSetup):
    def test_owner_can_promote_member(self):
        guard_role_change(Membership.objects, self.m_owner, self.m_alice, "admin")
        self.m_alice.role = "admin"  # mimic save
        self.assertEqual("admin", self.m_alice.role)

    def test_non_owner_cannot_change_roles(self):
        with self.assertRaises(GuardError):
            guard_role_change(Membership.objects, self.m_bob, self.m_alice, "owner")  # admin tries to promote

    def test_self_demote_blocked(self):
        with self.assertRaises(GuardError):
            guard_role_change(Membership.objects, self.m_owner, self.m_owner, "admin")

    def test_last_owner_cannot_be_demoted(self):
        # Only one owner – cannot demote them
        with self.assertRaises(GuardError):
            guard_role_change(Membership.objects, self.m_owner, self.m_owner, "member")

    def test_toggle_active_blocks_last_owner_deactivation(self):
        with self.assertRaises(GuardError):
            guard_toggle_active(Membership.objects, self.m_owner, self.m_owner, False)

    def test_owner_can_deactivate_other_member(self):
        guard_toggle_active(Membership.objects, self.m_owner, self.m_alice, False)
        self.m_alice.is_active = False
        self.assertFalse(self.m_alice.is_active)

class InvitationViewsTests(BaseSetup):
    def setUp(self):
        super().setUp()
        self.client = Client()

    def test_owner_can_create_invitation(self):
        self.client.force_login(self.owner)
        url = reverse("org-invite-create", kwargs={"org_id": self.org.id})
        res = self.client.post(url, {"email": "new@example.com", "role": "member"})
        self.assertEqual(res.status_code, 200)
        self.assertTrue(OrgInvite.objects.filter(org=self.org, email="new@example.com").exists())

    def test_admin_can_create_invitation(self):
        self.client.force_login(self.bob)  # admin
        url = reverse("org-invite-create", kwargs={"org_id": self.org.id})
        res = self.client.post(url, {"email": "x@example.com", "role": "member"})
        self.assertEqual(res.status_code, 200)

    def test_member_cannot_create_invitation(self):
        self.client.force_login(self.alice)  # member
        url = reverse("org-invite-create", kwargs={"org_id": self.org.id})
        res = self.client.post(url, {"email": "nope@example.com", "role": "member"})
        # We re-render members block with error; 200 but no invite is created
        self.assertEqual(res.status_code, 200)
        self.assertFalse(OrgInvite.objects.filter(org=self.org, email="nope@example.com").exists())
from django.test import TestCase

# Create your tests here.
