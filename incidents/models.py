from datetime import timedelta
from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.timesince import timesince, timeuntil
from orgs.models import Org, Site


def incident_upload_path(instance, filename):
    # e.g. incidents/42/2025/08/13/filename.pdf
    return f"incidents/{instance.incident_id}/{timezone.now():%Y/%m/%d}/{filename}"


# ---------------------------
# Core Incident
# ---------------------------
class Incident(models.Model):
    class Status(models.TextChoices):
        OPEN = "open", "Open"
        REPORTED = "reported", "Reported"  # kept for backward compatibility

    # Keep org during transition; different related_name to avoid clashes
    org = models.ForeignKey(
        Org,
        on_delete=models.CASCADE,
        related_name="incidents_legacy",
        null=True,
        blank=True,
    )
    # Site-level ownership
    site = models.ForeignKey(
        Site,
        on_delete=models.CASCADE,
        related_name="incidents",
        null=True,
        blank=True,
    )

    title = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)

    aware_at = models.DateTimeField(null=True, blank=True)
    reported_at = models.DateTimeField(null=True, blank=True)  # legacy single "reported" moment

    report_reference = models.CharField(max_length=255, blank=True)
    report_notes = models.TextField(blank=True, default="")  # keep NOT NULL at DB level

    created_at = models.DateTimeField(auto_now_add=True)

    # Optional severity (use if you want auto-suggest/UI mapping later)
    class Severity(models.TextChoices):
        LOW = "low", "Low"
        MODERATE = "moderate", "Moderate"
        HIGH = "high", "High"
        CRITICAL = "critical", "Critical"

    severity = models.CharField(
        max_length=10, choices=Severity.choices, default=Severity.MODERATE, blank=True
    )

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return self.title or f"Incident {self.pk}"

    # ---- Deadlines (incident-level, legacy 72h rule) ----
    @property
    def deadline_at(self):
        """72h after aware_at, if set (legacy single clock)."""
        if not self.aware_at:
            return None
        return self.aware_at + timedelta(hours=72)

    # ---- Status helpers (legacy) ----
    @property
    def is_reported(self) -> bool:
        """Single source of truth for legacy UI."""
        return self.status == Incident.Status.REPORTED

    def save(self, *args, **kwargs):
        # Normalize notes so we never persist NULL
        if self.report_notes is None:
            self.report_notes = ""

        # Keep status and reported_at consistent (legacy behavior)
        if self.status == Incident.Status.OPEN:
            self.reported_at = None
        elif self.status == Incident.Status.REPORTED and self.reported_at is None:
            self.reported_at = timezone.now()

        super().save(*args, **kwargs)

    # ---- Filing quality (legacy) ----
    @property
    def filed_on_time(self) -> bool | None:
        """
        True  -> filed on/before deadline
        False -> filed after deadline
        None  -> can't determine (missing reported_at or deadline)
        """
        if not self.is_reported or not self.deadline_at or not self.reported_at:
            return None
        return self.reported_at <= self.deadline_at

    # ---- Obligation-aware helpers (new) ----
    @property
    def obligations(self):
        return self.obligation_set.all()

    @property
    def next_obligation_deadline(self):
        """Soonest unfiled obligation deadline, if any."""
        pending = self.obligations.filter(filed_at__isnull=True).order_by("deadline_at")
        return pending.first().deadline_at if pending.exists() else None

    @property
    def ofgem_obligation(self):
        return self.obligations.filter(authority=Obligation.Authority.OFGEM).first()

    @property
    def all_obligations_filed(self) -> bool:
        qs = self.obligations
        return qs.exists() and not qs.filter(filed_at__isnull=True).exists()

    # ---- UI text: prefer obligation clocks when present ----
    @property
    def timer_text(self) -> str:
        """
        For UI: text for the 'timer' column.
        Priority:
        - If obligations exist: show next obligation countdown/overdue.
        - Else fall back to legacy 72h incident-level timer.
        When reported (legacy): reflect on-time/late if determinable.
        """
        # If we’re tracking obligations, show the next pending one.
        if self.obligations.exists():
            # If everything filed, show the most recent filing summary.
            if self.all_obligations_filed:
                last = self.obligations.order_by("-filed_at").first()
                if last and last.deadline_at and last.filed_at:
                    return "all filed on time" if last.filed_at <= last.deadline_at else "all filed (some late)"
                return "all filed"
            # Pending – show time until the next deadline
            deadline = self.next_obligation_deadline
            if not deadline:
                return "—"
            now = timezone.now()
            if now < deadline:
                return f"{timeuntil(deadline, now)} left"
            return f"overdue by {timesince(deadline, now)}"

        # No obligations: fall back to legacy single timer logic
        if self.is_reported:
            if self.filed_on_time is None:
                return "filed"
            return "filed on time" if self.filed_on_time else "filed late"

        if not self.deadline_at:
            return "—"

        now = timezone.now()
        if now < self.deadline_at:
            return f"{timeuntil(self.deadline_at, now)} left"
        return f"overdue by {timesince(self.deadline_at, now)}"

    @property
    def timer_css(self) -> str:
        """
        Optional: CSS hint for coloring the timer text.
        Red when overdue; green when explicitly 'on time'.
        """
        # Obligation‑aware coloring
        if self.obligations.exists():
            deadline = self.next_obligation_deadline
            if deadline and timezone.now() > deadline:
                return "text-red-600"
            # If everything filed, show green if all on time
            if self.all_obligations_filed:
                any_late = self.obligations.filter(filed_at__gt=models.F("deadline_at")).exists()
                return "text-green-600" if not any_late else ""
            return ""
        # Legacy fallback
        if self.is_reported:
            if self.filed_on_time is None:
                return ""
            return "text-green-600" if self.filed_on_time else "text-red-600"
        if self.deadline_at and timezone.now() > self.deadline_at:
            return "text-red-600"
        return ""


# ---------------------------
# Per‑obligation tracking (new)
# ---------------------------
class Obligation(models.Model):
    class Authority(models.TextChoices):
        OFGEM = "OFGEM", "Ofgem"
        ICO = "ICO", "ICO"
        CUSTOMERS = "CUSTOMERS", "Customers"
        INSURER = "INSURER", "Insurer"

    incident = models.ForeignKey(Incident, on_delete=models.CASCADE)
    authority = models.CharField(max_length=16, choices=Authority.choices)
    deadline_at = models.DateTimeField()
    filed_at = models.DateTimeField(null=True, blank=True)
    submission_ref = models.CharField(max_length=120, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("deadline_at", "id")

    def __str__(self):
        return f"{self.get_authority_display()} obligation for Incident {self.incident_id}"

    @property
    def is_filed(self) -> bool:
        return self.filed_at is not None

    @property
    def on_time(self) -> bool | None:
        if not self.filed_at or not self.deadline_at:
            return None
        return self.filed_at <= self.deadline_at


def create_default_obligations(incident: Incident):
    """
    Helper to seed common obligations: Ofgem 72h, ICO 72h.
    Call this in your create view after Incident is saved.
    """
    base = incident.aware_at or timezone.now()
    defaults = [
        (Obligation.Authority.OFGEM, base + timedelta(hours=72)),
        (Obligation.Authority.ICO, base + timedelta(hours=72)),
    ]
    for authority, deadline in defaults:
        Obligation.objects.get_or_create(
            incident=incident,
            authority=authority,
            defaults={"deadline_at": deadline},
        )


# ---------------------------
# Decision log (optional, used by UI if you add the tab)
# ---------------------------
class DecisionLog(models.Model):
    incident = models.ForeignKey(Incident, on_delete=models.CASCADE, related_name="decisions")
    decision = models.TextField()
    rationale = models.TextField(blank=True, default="")
    privileged = models.BooleanField(default=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="incident_decisions",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return f"Decision #{self.pk} on Incident {self.incident_id}"


# ---------------------------
# Stakeholders / approvals (optional)
# ---------------------------
class IncidentStakeholder(models.Model):
    class Role(models.TextChoices):
        COMMANDER = "commander", "Incident Commander"
        TECH_LEAD = "tech_lead", "Technical Lead"
        COMMS = "comms", "Comms Lead"
        LEGAL = "legal", "Legal"
        DPO = "dpo", "DPO"
        RISK = "risk", "Risk/2nd line"

    incident = models.ForeignKey(Incident, on_delete=models.CASCADE, related_name="stakeholders")
    role = models.CharField(max_length=32, choices=Role.choices)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="incident_roles",
    )
    required_approver = models.BooleanField(default=False)

    class Meta:
        unique_together = ("incident", "role")

    def __str__(self):
        return f"{self.get_role_display()} on Incident {self.incident_id}"


# ---------------------------
# Notes & attachments (kept as-is)
# ---------------------------
class IncidentNote(models.Model):
    incident = models.ForeignKey(Incident, on_delete=models.CASCADE, related_name="notes")
    body = models.TextField()
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="incident_notes",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return f"Note #{self.pk} on Incident {self.incident_id}"


class IncidentAttachment(models.Model):
    incident = models.ForeignKey(Incident, on_delete=models.CASCADE, related_name="attachments")
    file = models.FileField(upload_to=incident_upload_path)
    label = models.CharField(max_length=255, blank=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="incident_attachments",
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-uploaded_at",)

    def __str__(self):
        return f"Attachment #{self.pk} on Incident {self.incident_id}"

# models.py (inside class Obligation)
from django.utils.timesince import timesince, timeuntil
from django.utils import timezone

@property
def timer_text(self) -> str:
    """
    UI-friendly status:
      - Open:  'X left' or 'overdue by Y'
      - Filed: 'filed on time' or 'filed late'
    """
    if self.filed_at:
        if not self.deadline_at:
            return "filed"
        return "filed on time" if self.filed_at <= self.deadline_at else "filed late"

    if not self.deadline_at:
        return "—"

    now = timezone.now()
    if now < self.deadline_at:
        return f"{timeuntil(self.deadline_at, now)} left"
    return f"overdue by {timesince(self.deadline_at, now)}"

@property
def timer_css(self) -> str:
    """
    Optional CSS hint for coloring:
      - green when explicitly on-time
      - red when overdue or late
    """
    if self.filed_at and self.deadline_at:
        return "text-green-600" if self.filed_at <= self.deadline_at else "text-red-600"
    if self.deadline_at and timezone.now() > self.deadline_at:
        return "text-red-600"
    return ""
