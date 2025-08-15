from __future__ import annotations

from datetime import timedelta
import secrets

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.text import slugify


class Org(models.Model):
    # Keep the field name "user" because other code queries org__user
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="orgs",
    )
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    def __str__(self) -> str:  # pragma: no cover
        return self.name


class Membership(models.Model):
    # ---- role constants & choices (used by guards etc.) ----
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    ROLES = [(OWNER, "Owner"), (ADMIN, "Admin"), (MEMBER, "Member")]
    # -------------------------------------------------------

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

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.user} @ {self.org} ({self.role})"

    @property
    def is_owner(self) -> bool:
        return self.role == self.OWNER

    @property
    def is_admin(self) -> bool:
        return self.role in {self.OWNER, self.ADMIN}


class OrgInvite(models.Model):
    email = models.EmailField()
    org = models.ForeignKey("orgs.Org", on_delete=models.CASCADE, related_name="invites")
    role = models.CharField(max_length=10, choices=Membership.ROLES, default=Membership.MEMBER)
    token = models.CharField(max_length=64, unique=True, editable=False)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="sent_invites",
    )
    cancelled_at = models.DateTimeField(null=True, blank=True)

    def save(self, *args, **kwargs):
        if not self.token:
            self.token = secrets.token_urlsafe(32)
        if not self.expires_at:
            self.expires_at = timezone.now() + timedelta(days=7)
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


# ---------------------------
# Unified Site model (single!)
# ---------------------------
class Site(models.Model):
    org = models.ForeignKey(Org, on_delete=models.CASCADE, related_name="sites")
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200, blank=True)

    # Legacy freeform address (kept for backwards compatibility)
    address = models.TextField(
        blank=True,
        help_text="Legacy address (prefer structured fields below).",
    )

    created_at = models.DateTimeField(auto_now_add=True, editable=False)

    # --- Structured fields used for Annex E / reporting ---

    class EssentialService(models.TextChoices):
        ELECTRICITY = "electricity", "Electricity"
        GAS = "gas", "Gas"
        OTHER = "other", "Other"

    essential_service = models.CharField(
        max_length=32,
        choices=EssentialService.choices,
        default=EssentialService.ELECTRICITY,
    )

    NETWORK_ROLE_CHOICES = [
        ("generator", "Generator"),
        ("transmission", "Transmission operator"),
        ("distribution", "Distribution operator"),
        ("supplier", "Supplier"),
        ("gas_transmission", "Gas transmission"),
        ("gas_distribution", "Gas distribution"),
        ("storage", "Storage"),
        ("lng", "LNG"),
        ("other", "Other"),
    ]
    network_role = models.CharField(
        max_length=32,
        choices=NETWORK_ROLE_CHOICES,
        blank=True,
        default="distribution",
    )

    eic_code = models.CharField(max_length=32, blank=True)
    timezone = models.CharField(max_length=64, default="Europe/London")

    # Structured address
    address_line1 = models.CharField(max_length=255, blank=True)
    address_line2 = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=128, blank=True)
    postcode = models.CharField(max_length=32, blank=True)
    country_code = models.CharField(max_length=2, default="GB")

    # Primary incident reporting contact
    contact_name = models.CharField(max_length=128, blank=True)
    contact_role = models.CharField(max_length=128, blank=True)
    contact_email = models.EmailField(blank=True)
    contact_phone = models.CharField(max_length=64, blank=True)

    # Out-of-hours & privacy contact
    ooh_phone = models.CharField("Out-of-hours phone", max_length=64, blank=True)
    dpo_email = models.EmailField("DPO / privacy email", blank=True)

    class Meta:
        unique_together = ("org", "name")
        ordering = ("name",)

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)[:200]
        super().save(*args, **kwargs)

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.org.name} — {self.name}"
