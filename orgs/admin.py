# orgs/admin.py
from django.contrib import admin
from django import forms
from .models import Org, Membership, OrgInvite
from compliance_app.models import ComplianceRecord

# Inline only — do NOT register ComplianceRecord here
class ComplianceRecordInlineForm(forms.ModelForm):
    class Meta:
        model = ComplianceRecord
        fields = ("requirement", "status")
        widgets = {
            "requirement": forms.Textarea(
                attrs={"rows": 3, "cols": 80, "style": "min-width: 40em;"}
            ),
        }

class ComplianceRecordInline(admin.StackedInline):
    model = ComplianceRecord
    form = ComplianceRecordInlineForm
    extra = 1
    fields = ("requirement", "status")
    can_delete = True

@admin.register(Org)
class OrgAdmin(admin.ModelAdmin):
    # Adjust these fields to match your Org model
    list_display = ("name", "user", "created_at")
    search_fields = ("name", "user__username")
    list_filter = ("created_at",)
    inlines = [ComplianceRecordInline]

@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "org", "role", "is_active", "accepted_at")
    list_filter = ("role", "is_active", "org")
    search_fields = ("user__email", "user__username", "org__name")

@admin.register(OrgInvite)
class OrgInviteAdmin(admin.ModelAdmin):
    list_display = ("email", "org", "role", "expires_at", "used_at")
    list_filter = ("role", "org")
    search_fields = ("email", "org__name")
