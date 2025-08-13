import django_filters
from .models import Org

class OrgFilter(django_filters.FilterSet):
    name = django_filters.CharFilter(
        field_name="name", lookup_expr="icontains",
        label="Name contains",
        help_text="Case-insensitive substring match on organisation name."
    )
    created_after = django_filters.IsoDateTimeFilter(
        field_name="created_at", lookup_expr="gte",
        label="Created after",
        help_text="ISO 8601 datetime (e.g. 2025-08-12T09:00:00Z)."
    )
    created_before = django_filters.IsoDateTimeFilter(
        field_name="created_at", lookup_expr="lte",
        label="Created before",
        help_text="ISO 8601 datetime (e.g. 2025-08-12T23:59:59Z)."
    )

    class Meta:
        model = Org
        fields = ["name", "created_at"]
