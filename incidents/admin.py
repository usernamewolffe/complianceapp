from django.contrib import admin
from .models import Incident, IncidentUpdate, IncidentAttachment

@admin.register(Incident)
class IncidentAdmin(admin.ModelAdmin):
    list_display = ("id", "org", "title", "status", "severity", "aware_at", "deadline_at", "is_overdue")
    list_filter = ("status", "severity", "classification", "org")
    search_fields = ("title", "description")

admin.site.register(IncidentUpdate)
admin.site.register(IncidentAttachment)

from django.contrib import admin

# Register your models here.
