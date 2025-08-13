from django.db import models
from orgs.models import Org

class ComplianceRecord(models.Model):
    org = models.ForeignKey(Org, on_delete=models.CASCADE, related_name="compliance_records")
    requirement = models.CharField(max_length=255)
    status = models.CharField(max_length=50, choices=[
        ('pending', 'Pending'),
        ('complete', 'Complete'),
        ('failed', 'Failed')
    ])
    last_updated = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.org.name} - {self.requirement} ({self.status})"
