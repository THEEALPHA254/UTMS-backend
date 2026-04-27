# permissions.py
from rest_framework.permissions import BasePermission
from .models import *


class IsStaffOrAdmin(BasePermission):
    """Allows access only to users with role=staff or role=admin."""
    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and request.user.role in (User.Role.STAFF, User.Role.ADMIN)
        )


class IsAdminRole(BasePermission):
    """Allows access only to users with role=admin."""
    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and request.user.role == User.Role.ADMIN
        )


class IsOwnerOrAdmin(BasePermission):
    """Object-level: owner or admin can access."""
    def has_object_permission(self, request, view, obj):
        if request.user.role == User.Role.ADMIN:
            return True
        # obj may be a User or a profile with .user
        owner = obj if isinstance(obj, type(request.user)) else obj.user
        return owner == request.user