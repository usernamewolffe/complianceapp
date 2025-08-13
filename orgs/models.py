# orgs/models.py
from django.conf import settings
from django.db import models
from django.utils import timezone
import secrets


class Org(models.Model):
    # keep the field name "user" because other code queries org__user
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,  # use configured user model
        on_delete=models.CASCADE,
        related_name="orgs",
    )
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class Membership(models.Model):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    ROLES = [(OWNER, "Owner"), (ADMIN, "Admin"), (MEMBER, "Member")]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    org = models.ForeignKey(
        "orgs.Org",
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    role = models.CharField(max_length=10, choices=ROLES, default=MEMBER)
    is_active = models.BooleanField(default=True)
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    invited_at = models.DateTimeField(null=True, blank=True)
    accepted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ("user", "org")

    def __str__(self):
        return f"{self.user} @ {self.org} ({self.role})"

    @property
    def is_owner(self):
        return self.role == self.OWNER

    @property
    def is_admin(self):
        return self.role in {self.OWNER, self.ADMIN}


class OrgInvite(models.Model):
    email = models.EmailField()
    org = models.ForeignKey("orgs.Org", on_delete=models.CASCADE, related_name="invites")
    role = models.CharField(max_length=10, choices=Membership.ROLES, default=Membership.MEMBER)
    token = models.CharField(max_length=64, unique=True, editable=False)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="sent_invites"
    )
    cancelled_at = models.DateTimeField(null=True, blank=True)

    def save(self, *args, **kwargs):
        if not self.token:
            self.token = secrets.token_urlsafe(32)
        if not self.expires_at:
            self.expires_at = timezone.now() + timezone.timedelta(days=7)
        super().save(*args, **kwargs)

    @property
    def status(self) -> str:
        if self.used_at:
            return "ACCEPTED"
        if self.cancelled_at or (self.expires_at and self.expires_at < timezone.now()):
            return "CANCELLED"
        return "PENDING"

    @property
    def is_pending(self) -> bool:
        return self.status == "PENDING"
