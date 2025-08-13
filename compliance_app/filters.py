# compliance_app/filters.py
import django_filters
from .models import ComplianceRecord
from orgs.models import Org


class ComplianceRecordFilter(django_filters.FilterSet):
    requirement = django_filters.CharFilter(
        field_name="requirement",
        lookup_expr="icontains",
        label="Requirement contains",
        help_text="Case-insensitive substring match on the requirement text."
    )
    status = django_filters.MultipleChoiceFilter(
        choices=ComplianceRecord._meta.get_field("status").choices,
        label="Status",
        help_text="Repeat the parameter for multiple values, e.g. ?status=pending&status=failed."
    )
    last_updated_after = django_filters.IsoDateTimeFilter(
        field_name="last_updated",
        lookup_expr="gte",
        label="Updated after",
        help_text="ISO 8601 datetime (e.g. 2025-08-12T15:00:00Z)."
    )
    last_updated_before = django_filters.IsoDateTimeFilter(
        field_name="last_updated",
        lookup_expr="lte",
        label="Updated before",
        help_text="ISO 8601 datetime (e.g. 2025-08-12T23:59:59Z)."
    )
    org = django_filters.ModelChoiceFilter(
        queryset=Org.objects.none(),
        label="Organisation",
        help_text="Filter by organisation ID (limited to your orgs)."
    )

    class Meta:
        model = ComplianceRecord
        # Only model fields are required here; custom filter names are defined above.
        fields = ["org", "status", "requirement", "last_updated"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = getattr(self, "request", None)
        if request and request.user.is_authenticated:
            # Limit org choices to the current user's orgs
            self.filters["org"].queryset = Org.objects.filter(user=request.user)
