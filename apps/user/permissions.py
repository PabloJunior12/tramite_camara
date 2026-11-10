from rest_framework.permissions import BasePermission


class IsAdminRole(BasePermission):
    message = "No tienes permisos para gestionar usuarios."

    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and request.user.role == "ADMIN"
        )