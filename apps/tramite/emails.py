import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

logger = logging.getLogger(__name__)

def send_procedure_approved_email(procedure):
    recipient = procedure.sender_email

    if not recipient:
        return False

    context = {
        "sender_name": procedure.sender_name or "usuario",
        "procedure_code": procedure.code,
        "subject": procedure.subject,
        "status": procedure.get_status_display(),
    }

    text_body = (
        f"Estimado(a) {context['sender_name']}:\n\n"
        "Le informamos que su solicitud ha sido aprobada.\n\n"
        f"Código de trámite: {procedure.code}\n"
        f"Asunto: {procedure.subject}\n"
        f"Estado: {procedure.get_status_display()}\n\n"
        "Conserve este mensaje para futuras consultas.\n\n"
        "Mesa de Partes"
    )

    html_body = render_to_string(
        "emails/procedure_approved.html",
        context,
    )

    try:
        email = EmailMultiAlternatives(
            subject=f"Solicitud aprobada — {procedure.code}",
            body=text_body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[recipient],
        )
        email.attach_alternative(html_body, "text/html")
        email.send(fail_silently=False)
        return True
    except Exception:
        logger.exception(
            "Error enviando correo de aprobación del trámite %s",
            procedure.pk,
        )
        return False

def send_procedure_rejected_email(procedure):
    recipient = procedure.sender_email

    if not recipient:
        return False

    context = {
        "sender_name": procedure.sender_name or "usuario",
        "procedure_code": procedure.code,
        "subject": procedure.subject,
        "status": procedure.get_status_display(),
        "rejection_reason": procedure.rejection_reason,
    }

    text_body = (
        f"Estimado(a) {context['sender_name']}:\n\n"
        "Le informamos que su solicitud no fue aprobada.\n\n"
        f"Código de trámite: {procedure.code}\n"
        f"Asunto: {procedure.subject}\n"
        f"Estado: {procedure.get_status_display()}\n\n"
        "Motivo del rechazo:\n"
        f"{procedure.rejection_reason}\n\n"
        "Si necesita realizar una consulta, comuníquese con Mesa de Partes.\n\n"
        "Mesa de Partes"
    )

    html_body = render_to_string(
        "emails/procedure_rejected.html",
        context,
    )

    try:
        email = EmailMultiAlternatives(
            subject=f"Actualización de solicitud — {procedure.code}",
            body=text_body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[recipient],
        )
        email.attach_alternative(html_body, "text/html")
        email.send(fail_silently=False)
        return True
    except Exception:
        logger.exception(
            "Error enviando correo de rechazo del trámite %s",
            procedure.pk,
        )
        return False

def send_procedure_received_email(procedure):
    recipient = procedure.sender_email

    if not recipient:
        return False

    context = {
        "sender_name": procedure.sender_name or "usuario",
        "procedure_code": procedure.code,
        "subject": procedure.subject,
        "status": procedure.get_status_display(),
    }

    text_body = (
        f"Estimado(a) {context['sender_name']}:\n\n"
        "Confirmamos la recepción de su solicitud.\n\n"
        f"Código de trámite: {procedure.code}\n"
        f"Asunto: {procedure.subject}\n"
        f"Estado: {procedure.get_status_display()}\n\n"
        "Conserve este mensaje para futuras consultas.\n\n"
        "Mesa de Partes"
    )

    html_body = render_to_string(
        "emails/procedure_received.html",
        context,
    )

    try:
        email = EmailMultiAlternatives(
            subject=f"Solicitud recibida — {procedure.code}",
            body=text_body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[recipient],
        )
        email.attach_alternative(html_body, "text/html")
        email.send(fail_silently=False)
        return True
    except Exception:
        logger.exception(
            "Error enviando correo de recepción del trámite %s",
            procedure.pk,
        )
        return False