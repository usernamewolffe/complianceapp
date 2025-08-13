from rest_framework import permissions

class ReadOnlyOrAdmin(permissions.BasePermission):
    """
    Custom permission:
    - Anyone can read (GET, HEAD, OPTIONS)
    - Only staff/admin users can write (POST, PUT, PATCH, DELETE)
    """
    def has_permission(self, request, view):
        # Allow safe methods for everyone
        if request.method in permissions.SAFE_METHODS:
            return True
        # Allow writes only if the user is staff/admin
        return bool(request.user and request.user.is_staff)
