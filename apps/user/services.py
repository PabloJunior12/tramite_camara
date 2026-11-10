from .models import Module, UserPermission

def get_allowed_modules(user):
    # Si es staff, mostrar todos los módulos
    if user.is_staff:
        return Module.objects.filter(
            parent__isnull=True
        ).order_by("order")

    # Obtener módulos asignados al usuario
    module_ids = list(
        UserPermission.objects.filter(user=user)
        .values_list("module_id", flat=True)
    )

    # Incluir los padres automáticamente
    allowed = set(module_ids)

    def add_parents(module):
        if module.parent_id and module.parent_id not in allowed:
            allowed.add(module.parent_id)
            add_parents(module.parent)

    for module in Module.objects.filter(id__in=module_ids).select_related("parent"):
        add_parents(module)

    # Devolver módulos raíz permitidos
    return Module.objects.filter(
        id__in=allowed,
        parent__isnull=True
    ).order_by("order")