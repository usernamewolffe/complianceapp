# incidents/admin.py
from django.contrib import admin
from .models import Incident, IncidentNote, IncidentAttachment



@admin.register(Incident)
class IncidentAdmin(admin.ModelAdmin):
    # keep to fields that actually exist on your Incident model
    list_display = ("id", "title", "status")
    search_fields = ("title", "report_reference", "report_notes")
    list_filter = ("status",)  # add more later if/when fields exist


@admin.register(IncidentNote)
class IncidentNoteAdmin(admin.ModelAdmin):
    list_display = ("id", "incident")
    search_fields = ("body",)


@admin.register(IncidentAttachment)
class IncidentAttachmentAdmin(admin.ModelAdmin):
    list_display = ("id", "incident")
    search_fields = ("label",)

