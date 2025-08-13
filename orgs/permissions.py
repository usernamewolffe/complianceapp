# orgs/permissions.py
from rest_framework import permissions
from .models import Membership
from orgs.models import Org

class IsOrgMember(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        org = obj if isinstance(obj, Org) else getattr(obj, "org", None)
        if not org or not request.user.is_authenticated:
            return False
        return Membership.objects.filter(org=org, user=request.user, is_active=True).exists()

class RequireRole(permissions.BasePermission):
    order = {"member": 1, "admin": 2, "owner": 3}
    def __init__(self, min_role="member"):
        self.min_role = min_role
    def has_object_permission(self, request, view, obj):
        org = obj if isinstance(obj, Org) else getattr(obj, "org", None)
        if not org or not request.user.is_authenticated:
            return False
        m = Membership.objects.filter(org=org, user=request.user, is_active=True).first()
        return bool(m and self.order[m.role] >= self.order[self.min_role])
