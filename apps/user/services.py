from .models import Module, UserPermission

def get_allowed_modules(user):

    # Los solicitantes no tienen acceso al menú administrativo
    if user.role == "APPLICANT":
        return Module.objects.none()

    # Administradores y staff ven todos los módulos
    if user.is_staff or user.role == "ADMIN":
        return Module.objects.filter(
            parent__isnull=True
        ).order_by("order")

    # Los demás usuarios ven todos los módulos
    return Module.objects.filter(
        parent__isnull=True
    ).order_by("order")