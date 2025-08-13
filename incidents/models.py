# incidents/models.py
from datetime import timedelta
from django.conf import settings
from django.db import models
from django.utils import timezone


class Incident(models.Model):
    class Classification(models.TextChoices):
        AVAILABILITY = "availability", "Availability"
        INTEGRITY = "integrity", "Integrity"
        CONFIDENTIALITY = "confidentiality", "Confidentiality"
        OTHER = "other", "Other"

    class Severity(models.TextChoices):
        LOW = "low", "Low"
        MEDIUM = "medium", "Medium"
        HIGH = "high", "High"
        CRITICAL = "critical", "Critical"

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        CONTAINED = "contained", "Contained"
        RESOLVED = "resolved", "Resolved"
        CLOSED = "closed", "Closed"

    org = models.ForeignKey("orgs.Org", on_delete=models.CASCADE, related_name="incidents")
    title = models.CharField(max_length=255)
    classification = models.CharField(max_length=32, choices=Classification.choices, default=Classification.OTHER)
    severity = models.CharField(max_length=16, choices=Severity.choices, default=Severity.MEDIUM)
    aware_at = models.DateTimeField(help_text="When you became aware (starts the 72h clock)")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.OPEN)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="incident_owner"
    )
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=("org", "status")),
            models.Index(fields=("org", "aware_at")),
        ]

    @property
    def deadline_at(self):
        return self.aware_at + timedelta(hours=72) if self.aware_at else None

    @property
    def is_overdue(self):
        return bool(self.deadline_at and timezone.now() > self.deadline_at)

    @property
    def seconds_to_deadline(self) -> int | None:
        if not self.deadline_at:
            return None
        return int((self.deadline_at - timezone.now()).total_seconds())

    def __str__(self):
        return f"{self.org} – {self.title}"


class IncidentUpdate(models.Model):
    incident = models.ForeignKey(Incident, on_delete=models.CASCADE, related_name="updates")
    note = models.TextField()
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return f"Update #{self.pk} on {self.incident_id}"


class IncidentAttachment(models.Model):
    incident = models.ForeignKey(Incident, on_delete=models.CASCADE, related_name="attachments")
    file = models.FileField(upload_to="incidents/%Y/%m/%d/")
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Attachment #{self.pk} on {self.incident_id}"
