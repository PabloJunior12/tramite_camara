
from django.utils import timezone
from django.db.models import Q
from django.core.exceptions import ValidationError
from django.db import transaction
from .models import Procedure, ArbitrationCase, CaseSequence



ALLOWED_TRANSITIONS = {
    Procedure.Status.RECEIVED: {
        Procedure.Status.UNDER_REVIEW,
    },
    Procedure.Status.UNDER_REVIEW: {
        Procedure.Status.OBSERVED,
        Procedure.Status.APPROVED,
        Procedure.Status.REJECTED,
    },
    Procedure.Status.OBSERVED: {
        Procedure.Status.UNDER_REVIEW,
    },
    Procedure.Status.APPROVED: {
        Procedure.Status.REGISTERED,
    },
    Procedure.Status.REJECTED: set(),
    Procedure.Status.REGISTERED: set(),
}

@transaction.atomic
def change_procedure_status(
    procedure_id,
    new_status,
    reviewer,
    observation="",
    rejection_reason="",
):
    procedure = (
        Procedure.objects
        .select_for_update()
        .get(pk=procedure_id)
    )

    allowed = ALLOWED_TRANSITIONS.get(
        procedure.status,
        set(),
    )

    if new_status not in allowed:
        raise ValidationError(
            f"No se puede cambiar de "
            f"{procedure.get_status_display()} a "
            f"{Procedure.Status(new_status).label}."
        )

    if new_status == Procedure.Status.OBSERVED:
        if not observation.strip():
            raise ValidationError(
                "Debes indicar la observación."
            )

        procedure.review_observation = observation.strip()

    if new_status == Procedure.Status.REJECTED:
        if not rejection_reason.strip():
            raise ValidationError(
                "Debes indicar el motivo del rechazo."
            )

        procedure.rejection_reason = (
            rejection_reason.strip()
        )

    if new_status == Procedure.Status.UNDER_REVIEW:
        # Limpiar las observaciones anteriores al iniciar
        # una nueva revisión después de la subsanación.
        if procedure.status == Procedure.Status.OBSERVED:
            procedure.review_observation = ""

    procedure.status = new_status
    procedure.reviewed_by = reviewer
    procedure.reviewed_at = timezone.now()

    procedure.save(
        update_fields=[
            "status",
            "reviewed_by",
            "reviewed_at",
            "review_observation",
            "rejection_reason",
        ]
    )

    return procedure

@transaction.atomic
def create_arbitration_case(user, **case_data):
    year = timezone.localdate().year

    sequence, _ = CaseSequence.objects.get_or_create(
        year=year,
        defaults={"last_number": 0},
    )

    sequence = CaseSequence.objects.select_for_update().get(
        pk=sequence.pk
    )

    sequence.last_number += 1
    sequence.save(update_fields=["last_number"])

    case = ArbitrationCase.objects.create(
        code=f"{sequence.last_number:03d}-{year}-CCH",
        created_by=user,
        **case_data,
    )

    return case