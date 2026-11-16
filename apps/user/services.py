from .models import Module, User


def get_allowed_modules(user):

    # ADMIN y superusuarios tienen acceso completo.
    if user.role == User.Role.ADMIN or user.is_superuser:

        return Module.objects.filter(
            parent__isnull=True
        ).prefetch_related(
            "children"
        ).order_by("order", "name")

    # Módulos exclusivos de administradores.
    restricted_codes = [
        "usuarios-permisos",
    ]

    # Obtener módulos asignados, excluyendo los restringidos.
    assigned_ids = set(
        user.module_accesses.exclude(
            module__code__in=restricted_codes
        ).values_list(
            "module_id",
            flat=True
        )
    )

    if not assigned_ids:
        return Module.objects.none()

    # Obtener los módulos asignados.
    assigned_modules = Module.objects.filter(
        id__in=assigned_ids
    )

    # Identificar los padres.
    parent_ids = set(
        assigned_modules.exclude(
            parent__isnull=True
        ).values_list(
            "parent_id",
            flat=True
        )
    )

    allowed_ids = assigned_ids | parent_ids

    return Module.objects.filter(
        id__in=allowed_ids,
        parent__isnull=True
    ).prefetch_related(
        "children"
    ).order_by(
        "order", "name"
    )