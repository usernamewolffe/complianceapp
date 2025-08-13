from django.contrib import admin
from django import forms
from .models import ComplianceRecord
from orgs.models import Org

class ComplianceRecordAdminForm(forms.ModelForm):
    class Meta:
        model = ComplianceRecord
        fields = "__all__"
        widgets = {
            "requirement": forms.Textarea(
                attrs={"rows": 3, "cols": 80, "style": "min-width: 40em;"}
            ),
        }

@admin.register(ComplianceRecord)
class ComplianceRecordAdmin(admin.ModelAdmin):
    form = ComplianceRecordAdminForm
    list_display = ("requirement", "org", "status", "last_updated")
    search_fields = ("requirement", "org__name")
    list_filter = ("status", "last_updated")

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs if request.user.is_superuser else qs.filter(org__user=request.user)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "org" and not request.user.is_superuser:
            kwargs["queryset"] = Org.objects.filter(user=request.user)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)
