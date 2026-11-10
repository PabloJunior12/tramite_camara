
from django.utils import timezone
from django.db.models import Q
from .models import ProcedureSequence, Procedure

import django_filters


class ProcedureFilter(django_filters.FilterSet):

    # 🔍 BUSCADOR GLOBAL
    search = django_filters.CharFilter(method="filter_global")

    # filtros avanzados (los que ya tienes)
    code = django_filters.CharFilter(
        field_name="code",
        lookup_expr="icontains"
    )

    sender_name = django_filters.CharFilter(
        field_name="sender_name",
        lookup_expr="icontains"
    )

    date_from = django_filters.DateFilter(
        field_name="created_at",
        lookup_expr="date__gte"
    )
    date_to = django_filters.DateFilter(
        field_name="created_at",
        lookup_expr="date__lte"
    )

    def filter_global(self, queryset, name, value):
        return queryset.filter(
            Q(code__icontains=value) |
            Q(sender_name__icontains=value) |
            Q(subject__icontains=value)
        )

    class Meta:
        model = Procedure
        fields = [
            "search",
            "code",
            "sender_name",
            "date_from",
            "date_to",
        ]

def generate_procedure_code() -> str:
    year = timezone.localdate().year

    # Obtener o crear la secuencia del año
    sequence, _ = ProcedureSequence.objects.get_or_create(
        year=year,
        defaults={"last_number": 0},
    )

    # Bloquear la fila para evitar códigos duplicados
    sequence = (
        ProcedureSequence.objects
        .select_for_update()
        .get(pk=sequence.pk)
    )

    # Incrementar el correlativo
    sequence.last_number += 1
    sequence.save(update_fields=["last_number"])

    # Formato: 001-2026
    return f"{sequence.last_number:04d}-{year}"