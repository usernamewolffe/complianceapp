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
from django.contrib.auth import get_user_model
from django.urls import reverse
from orgs.models import Org, Membership, OrgInvite

User = get_user_model()

def mk_user(username):
    return User.objects.create_user(username=username, password="x")

class GuardTests(TestCase):
    def setUp(self):
        self.owner = mk_user("owner")
        self.admin = mk_user("admin")
        self.member = mk_user("member")
        self.other  = mk_user("other")
        self.org = Org.objects.create(user=self.owner, name="Org A")
        self.own_m  = Membership.objects.create(org=self.org, user=self.owner, role=Membership.OWNER)
        self.adm_m  = Membership.objects.create(org=self.org, user=self.admin, role=Membership.ADMIN)
        self.mem_m  = Membership.objects.create(org=self.org, user=self.member, role=Membership.MEMBER)

    def login(self, user):
        self.client.login(username=user.username, password="x")

    def test_only_owner_can_change_roles(self):
        self.login(self.admin)
        url = reverse("org-member-update", args=[self.org.id, self.mem_m.id])
        r = self.client.post(url, {"role": Membership.ADMIN})
        self.assertContains(r, "Only owners", status_code=200)

    def test_cannot_demote_last_owner(self):
        self.login(self.owner)
        url = reverse("org-member-update", args=[self.org.id, self.own_m.id])
        r = self.client.post(url, {"role": Membership.MEMBER})
        self.assertContains(r, "last Owner", status_code=200)

    def test_owner_cannot_self_demote(self):
        self.login(self.owner)
        url = reverse("org-member-update", args=[self.org.id, self.own_m.id])
        r = self.client.post(url, {"role": Membership.ADMIN})
        self.assertContains(r, "lower your own role", status_code=200)

    def test_cannot_deactivate_last_owner(self):
        self.login(self.owner)
        url = reverse("org-member-toggle", args=[self.org.id, self.own_m.id])
        r = self.client.post(url, {"active": "false"})
        self.assertContains(r, "last Owner", status_code=200)

    def test_cannot_deactivate_self(self):
        self.login(self.owner)
        url = reverse("org-member-toggle", args=[self.org.id, self.own_m.id])
        r = self.client.post(url, {"active": "0"})
        self.assertContains(r, "deactivate your own", status_code=200)

class InvitationTests(TestCase):
    def setUp(self):
        self.owner = mk_user("owner")
        self.org = Org.objects.create(user=self.owner, name="Org A")
        self.own_m = Membership.objects.create(org=self.org, user=self.owner, role=Membership.OWNER)

    def login(self, user):
        self.client.login(username=user.username, password="x")

    def test_invite_create_and_cancel(self):
        self.login(self.owner)
        create_url = reverse("org-invite-create", args=[self.org.id])
        r = self.client.post(create_url, {"email": "e@example.com", "role": Membership.MEMBER})
        self.assertContains(r, "Saved", status_code=200)
        inv = OrgInvite.objects.get(org=self.org, email="e@example.com")
        cancel_url = reverse("invitation_cancel", args=[self.org.id, inv.id])
        r2 = self.client.post(cancel_url)
        self.assertContains(r2, "Saved", status_code=200)
from django.test import TestCase

# Create your tests here.
