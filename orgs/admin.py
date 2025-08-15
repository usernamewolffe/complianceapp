from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.exceptions import FieldDoesNotExist

from .models import Org, Site, Membership  # adjust if your app path differs

# Optional: invitations model (only if you have it)
try:
    from .models import OrgInvite  # rename if your invite model is different
except Exception:
    OrgInvite = None

User = get_user_model()


# ---------- small helpers ----------

def model_has_field(model, name: str) -> bool:
    try:
        model._meta.get_field(name)
        return True
    except FieldDoesNotExist:
        return False
    except Exception:
        return False

def pick_fields(model, candidates):
    """Return only the field names that exist on the model."""
    return [n for n in candidates if model_has_field(model, n)]


# ---------- Inlines ----------

class MembershipInline(admin.TabularInline):
    model = Membership
    extra = 1
    # Common fields; we'll drop any that don't exist
    _base_fields = ["user", "role", "is_active", "created_at", "created"]
    fields = pick_fields(Membership, _base_fields)
    readonly_fields = pick_fields(Membership, ["created_at", "created"])
    # Use autocomplete if 'user' is a FK to your auth user
    autocomplete_fields = pick_fields(Membership, ["user"])
    show_change_link = True


# ---------- Admin registrations ----------

@admin.register(Org)
class OrgAdmin(admin.ModelAdmin):
    list_display = ("id", "name")
    search_fields = ("name",)
    inlines = [MembershipInline]


@admin.register(Site)
class SiteAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "org")
    list_filter = ("org",)
    search_fields = ("name",)
    actions = []

    # Optional: prevent deleting a site that has incidents attached
    def has_delete_permission(self, request, obj=None):
        if obj and hasattr(obj, "incidents") and obj.incidents.exists():
            return False
        return super().has_delete_permission(request, obj)


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    # Build list_display safely based on actual fields
    _base = ["id", "org", "user", "role", "is_active", "created_at", "created"]
    list_display = tuple(pick_fields(Membership, _base))
    # Fall back if your Membership doesn’t have role/is_active/timestamps
    if not list_display:
        list_display = ("id",)

    list_filter = tuple(pick_fields(Membership, ["org", "is_active", "role"]))
    search_fields = tuple(
        f for f in ["user__username", "user__email", "org__name"]  # these are OK even if role/timestamps missing
    )
    autocomplete_fields = pick_fields(Membership, ["org", "user"])
    readonly_fields = tuple(pick_fields(Membership, ["created_at", "created"]))

    @admin.action(description="Activate selected members")
    def activate(self, request, queryset):
        if model_has_field(Membership, "is_active"):
            queryset.update(is_active=True)

    @admin.action(description="Deactivate selected members")
    def deactivate(self, request, queryset):
        if model_has_field(Membership, "is_active"):
            queryset.update(is_active=False)

    actions = ["activate", "deactivate"]


# Optional: only register invite admin if the model exists
if OrgInvite is not None:
    class _BaseInviteAdmin(admin.ModelAdmin):
        # Safely pick columns from common invite fields
        _cols = ["id", "org", "email", "status", "created_at", "created"]
        list_display = tuple(pick_fields(OrgInvite, _cols)) or ("id",)
        list_filter = tuple(pick_fields(OrgInvite, ["org", "status"]))
        search_fields = tuple(f for f in ["email", "org__name"] if f)

    try:
        @admin.register(OrgInvite)
        class OrgInviteAdmin(_BaseInviteAdmin):
            pass
    except admin.sites.AlreadyRegistered:
        # If it was registered elsewhere, skip
        pass
