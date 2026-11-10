from django.db import models
from django.conf import settings
from django.utils.timezone import now
from django.core.validators import MinValueValidator
from django.db.models import Sum
from decimal import Decimal
import uuid
import os

from pathlib import Path

User = settings.AUTH_USER_MODEL

class SystemBackup(models.Model):

    BACKUP_TYPE_CHOICES = (
        ("daily", "Diario"),
        ("manual", "Manual"),
    )

    file_path = models.CharField(max_length=500)

    backup_type = models.CharField(
        max_length=10,
        choices=BACKUP_TYPE_CHOICES
    )

    size = models.BigIntegerField()

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    @property
    def filename(self):
        return os.path.basename(self.file_path)

    @property
    def size_mb(self):
        return round(self.size / (1024 * 1024), 2)

    def __str__(self):
        return self.filename

class GlobalBackup(models.Model):

    STATUS_CHOICES = (
        ("pending", "Pendiente"),
        ("success", "Exitoso"),
        ("failed", "Fallido"),
    )

    file_name = models.CharField(max_length=255)
    file_path = models.TextField()
    size_mb = models.DecimalField(max_digits=10, decimal_places=2, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        help_text="Usuario o CRON"
    )

    def __str__(self):
        
        return self.file_name

class Department(models.Model):

    id = models.CharField(primary_key=True,max_length=2)
    description = models.CharField(max_length=255,)
    active = models.BooleanField(default=True)

class Province(models.Model):

    id = models.CharField(primary_key=True, max_length=4)
    description = models.CharField(max_length=255)
    department = models.ForeignKey(Department, on_delete=models.CASCADE)
    active = models.BooleanField(default=True)

class District(models.Model):
    
    id = models.CharField(primary_key=True, max_length=6)
    description = models.CharField(max_length=255)
    province = models.ForeignKey(Province,on_delete=models.CASCADE)
    active = models.BooleanField(default=True, verbose_name='Activo')

class Company(models.Model):

    name = models.CharField(max_length=255, verbose_name="Nombre de la empresa")
    ruc = models.CharField(max_length=11, unique=True, verbose_name="RUC")
    address = models.CharField(max_length=255, verbose_name="Dirección", null=True, blank=True)
    phone = models.CharField(max_length=20, verbose_name="Teléfono", null=True, blank=True)
    email = models.EmailField(verbose_name="Correo electrónico", null=True, blank=True)
    logo = models.ImageField(upload_to="logos/", verbose_name="Logo", null=True, blank=True)

    def __str__(self):
        return self.name

class Document(models.Model):

    code = models.CharField(max_length=2, unique=True)
    name = models.CharField(max_length=100)
 
    def __str__(self):
        return self.name

class Area(models.Model):

    TYPE_CHOICES = [
        ("TE", "Tramite externo"),
        ("TI", "Tramite interno"),
        ("TV", "Tramite virtual"),
    ]

    name = models.CharField(max_length=100)
    code = models.CharField(max_length=3, unique=True, editable=False)
    state = models.BooleanField(default=True)
    type = models.CharField(max_length=10, choices=TYPE_CHOICES, default="TI")
    initials = models.CharField(max_length=50, null=True, blank=True)

    def save(self, *args, **kwargs):

        if not self.code:

            last= Area.objects.order_by('-id').first()

            next_number = 1 if not last else int(last.code) + 1

            self.code = str(next_number).zfill(3)

        super().save(*args, **kwargs)

    def __str__(self):

        return self.name

class UserArea(models.Model):

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='user_areas'
    )
    area = models.ForeignKey(
        Area,
        on_delete=models.CASCADE,
        related_name='area_users'
    )

    class Meta:
        unique_together = ('user', 'area')

    def save(self, *args, **kwargs):
        if self.user.agency_id != self.area.agency_id:
            raise ValueError(
                "El usuario no pertenece a la agencia del área"
            )
        super().save(*args, **kwargs)

class Specialty(models.Model):

    name = models.CharField(
        max_length=150,
        unique=True,
        verbose_name="Nombre de la especialidad",
    )

    def __str__(self):
        return self.name

class Subject(models.Model):

    name = models.CharField(
        max_length=150,
        unique=True,
        verbose_name="Nombre de la especialidad",
    )

    def __str__(self):
        return self.name

class ProceduralStage(models.Model):

    name = models.CharField(max_length=150, unique=True)

    def __str__(self):

        return self.name

class CaseLocation(models.Model):

    name = models.CharField(max_length=150, unique=True)

    def __str__(self):

        return self.name

# Árbitro

class ProcedureSequence(models.Model):

    year = models.PositiveIntegerField()
    last_number = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "Secuencia de procedimiento"
        verbose_name_plural = "Secuencias de procedimientos"
        constraints = [
            models.UniqueConstraint(
                fields=["year"],
                name="unique_procedure_sequence_year",
            )
        ]
        ordering = ["-year"]

    def __str__(self):
        return f"{self.year} - {self.last_number}"

class Procedure(models.Model):

    class AttachmentMode(models.TextChoices):
        ARCHIVOS = "archivos", "Archivos"
        ENLACE = "enlace", "Enlace"

    class Status(models.TextChoices):

        RECEIVED = "RECEIVED", "Recibida"
        UNDER_REVIEW = "UNDER_REVIEW", "En revisión"
        OBSERVED = "OBSERVED", "Observada"
        APPROVED = "APPROVED", "Aprobada"
        REJECTED = "REJECTED", "Rechazada"
        REGISTERED = "REGISTERED", "Expediente registrado"

    # --------------------------------------------------------
    # Identificación
    # --------------------------------------------------------

    code = models.CharField(
        max_length=30,
        unique=True,
        null=True,
        blank=True,
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.RECEIVED,
        db_index=True,
    )

    # --------------------------------------------------------
    # Datos del remitente
    # --------------------------------------------------------

    sender_dni = models.CharField(
        max_length=15,
        blank=True,
        null=True,
    )

    sender_name = models.CharField(
        max_length=255,
        blank=True,
        null=True,
    )

    sender_representante = models.CharField(
        max_length=255,
        blank=True,
        null=True,
    )

    sender_phone = models.CharField(
        max_length=20,
        blank=True,
        null=True,
    )

    sender_email = models.EmailField(
        blank=True,
        null=True,
    )

    # --------------------------------------------------------
    # Información presentada
    # --------------------------------------------------------

    subject = models.TextField()
    request_detail = models.TextField()

    is_virtual = models.BooleanField(default=True)

    is_annulled = models.BooleanField(default=False)
    is_blocked = models.BooleanField(default=False)

    # --------------------------------------------------------
    # Usuario que registra la presentación
    # --------------------------------------------------------

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_procedures",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
    )

    # --------------------------------------------------------
    # Revisión administrativa
    # --------------------------------------------------------

    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="reviewed_procedures",
    )

    reviewed_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    review_observation = models.TextField(
        null=True,
        blank=True,
    )

    rejection_reason = models.TextField(
        null=True,
        blank=True,
    )

    modoAdjuntos = models.CharField(
        max_length=10,
        choices=AttachmentMode.choices,
        default=AttachmentMode.ARCHIVOS,
    )

    enlaceArchivos = models.URLField(
        max_length=2048,
        blank=True,
        null=True,
    )

    class Meta:
        verbose_name = "Solicitud de mesa de partes"
        verbose_name_plural = "Solicitudes de mesa de partes"
        ordering = ["-created_at"]

        indexes = [
            models.Index(
                fields=["status", "created_at"],
                name="proc_status_created_idx",
            ),
            models.Index(
                fields=["sender_dni", "created_at"],
                name="proc_sender_created_idx",
            ),
        ]


    @property
    def has_files(self):
        return self.files.exists()

    def __str__(self):
        return self.code or f"Solicitud #{self.pk or 'nueva'}"

def procedure_file_path(instance, filename):
    extension = Path(filename).suffix.lower()

    return (
        f"procedures/"
        f"procedure_{instance.procedure_id}/"
        f"{uuid.uuid4().hex}{extension}"
    )

class ProcedureFile(models.Model):

    procedure = models.ForeignKey(
        Procedure,
        on_delete=models.CASCADE,
        related_name="files",
    )

    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="uploaded_procedure_files",
    )

    file = models.FileField(
        upload_to=procedure_file_path,
    )

    original_name = models.CharField(
        max_length=255,
        blank=True,
        default="",
    )

    description = models.CharField(
        max_length=255,
        blank=True,
        default="",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Documento adjunto"
        verbose_name_plural = "Documentos adjuntos"
        ordering = ["created_at"]

    @property
    def filename(self):
        return self.original_name or Path(self.file.name).name

    def __str__(self):
        return self.filename

class ProcedureHistory(models.Model):

    class Action(models.TextChoices):
        RECEIVED = "RECEIVED", "Solicitud recibida"
        REVIEW_STARTED = "REVIEW_STARTED", "Revisión iniciada"
        OBSERVED = "OBSERVED", "Solicitud observada"
        RESUBMITTED = "RESUBMITTED", "Solicitud subsanada"
        APPROVED = "APPROVED", "Solicitud aprobada"
        REJECTED = "REJECTED", "Solicitud rechazada"
        REGISTERED = "REGISTERED", "Expediente registrado"
        ANNULLED = "ANNULLED", "Solicitud anulada"

    procedure = models.ForeignKey(
        Procedure,
        on_delete=models.CASCADE,
        related_name="history",
    )

    action = models.CharField(
        max_length=20,
        choices=Action.choices,
        db_index=True,
    )

    previous_status = models.CharField(
        max_length=20,
        choices=Procedure.Status.choices,
        blank=True,
        default="",
    )

    new_status = models.CharField(
        max_length=20,
        choices=Procedure.Status.choices,
    )

    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="procedure_history_actions",
    )

    comment = models.TextField(
        blank=True,
        default="",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
    )

    class Meta:

        verbose_name = "Historial de procedimiento"
        verbose_name_plural = "Historial de procedimientos"
        ordering = ["-created_at"]

    def __str__(self):
        return (
            f"{self.procedure_id} - "
            f"{self.get_action_display()}"
        )

# MODELOS DEL EXPEDIENTE

def case_file_path(instance, filename):
    extension = Path(filename).suffix.lower()
    return f"cases/case_{instance.case_id}/{uuid.uuid4().hex}{extension}"

class CaseSequence(models.Model):

    year = models.PositiveIntegerField(unique=True)
    last_number = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-year"]

class ArbitrationCase(models.Model):

    class Status(models.TextChoices):

        ACTIVE = "ACTIVE", "Activo"
        CLOSED = "CLOSED", "Concluido"

    code = models.CharField(
        max_length=30,
        unique=True
    )

    # Procedimiento que origina el expediente.
    source_procedure = models.OneToOneField(
        Procedure,
        on_delete=models.PROTECT,
        related_name="arbitration_case",
        null=True,
        blank=True
    )

    # Árbitro principal asignado al expediente.
    arbitrator = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="arbitration_cases"
    )

    secretary_arbitrator = models.CharField(max_length=255)

    subject = models.ForeignKey(
        Subject,
        on_delete=models.PROTECT,
        related_name="arbitration_cases",
        verbose_name="Materia"
    )

    process = models.CharField(max_length=255, verbose_name="Proceso", null=True, blank=True)

    specialty = models.ForeignKey(
        Specialty,
        on_delete=models.PROTECT,
        related_name="arbitration_cases",
        verbose_name="Especialidad"
    )

    procedural_stage = models.ForeignKey(
        ProceduralStage,
        on_delete=models.PROTECT,
        related_name="arbitration_cases",
        verbose_name="Etapa procesal",
    )

    ubicacion = models.ForeignKey(
        CaseLocation,
        on_delete=models.PROTECT,
        related_name="arbitration_cases",
        verbose_name="Ubicación",
    )

    date_of_issue = models.DateField(null=True,blank=True)
    date_of_due = models.DateField(null=True, blank=True)
    reason_for_conclusion = models.TextField(null=True, blank=True)

     # Pestaña Demanda
    controversy_reason = models.TextField(null=True, blank=True)
    claims = models.TextField(null=True, blank=True)

    # arbitraje y cuantia
    arbitration_agreement = models.TextField(null=True, blank=True)
    designation_of_arbitrator = models.TextField(null=True, blank=True)
    amount_in_dispute = models.TextField(null=True, blank=True)

    observation = models.TextField(null=True, blank=True)

    status = models.CharField(max_length=20,choices=Status.choices,default=Status.ACTIVE,db_index=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT,related_name="created_arbitration_cases")
    created_at = models.DateTimeField(auto_now_add=True,db_index=True)
    closed_at = models.DateTimeField(null=True,blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.code

class CaseFile(models.Model):
    class StorageType(models.TextChoices):
        FILE = "FILE", "Archivo"
        LINK = "LINK", "Enlace"

    case = models.ForeignKey(
        ArbitrationCase,
        on_delete=models.CASCADE,
        related_name="files_case",
    )
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="uploaded_case_files",
    )

    storage_type = models.CharField(
        max_length=10,
        choices=StorageType.choices,
        default=StorageType.FILE,
    )
    file = models.FileField(upload_to=case_file_path, null=True, blank=True)
    external_url = models.URLField(max_length=2000, null=True, blank=True)

    original_name = models.CharField(max_length=255, blank=True, default="")
    description = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def filename(self):
        if self.original_name:
            return self.original_name
        if self.file:
            return Path(self.file.name).name
        return self.external_url or "Enlace"

    def __str__(self):
        return self.filename

class CaseObservation(models.Model):
    case = models.ForeignKey(
        ArbitrationCase,
        on_delete=models.CASCADE,
        related_name="observations",
    )
    content = models.TextField()
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="case_observations",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Observación de {self.case.code} ({self.created_at:%Y-%m-%d})"

class CaseNotification(models.Model):
    case = models.ForeignKey(
        ArbitrationCase,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    file = models.FileField(upload_to=case_file_path)
    original_name = models.CharField(max_length=255, blank=True, default="")
    description = models.CharField(max_length=255, blank=True, default="")
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="uploaded_case_notifications",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    @property
    def filename(self):
        if self.original_name:
            return self.original_name
        if self.file:
            return Path(self.file.name).name
        return "Notificación"

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.filename

class CaseParty(models.Model):
    
    class Role(models.TextChoices):
        CLAIMANT = "CLAIMANT", "Demandante"
        RESPONDENT = "RESPONDENT", "Demandado"

    case = models.ForeignKey(
        ArbitrationCase,
        on_delete=models.PROTECT,
        related_name="parties",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="case_participations",
    )
    role = models.CharField(max_length=20, choices=Role.choices)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["case", "user", "role"],
                name="unique_user_role_per_case",
            ),
        ]

    def __str__(self):
        return f"{self.user} - {self.case.code} - {self.get_role_display()}"

class CasePartyLawyer(models.Model):

    class Status(models.TextChoices):

        ACTIVE = "ACTIVE", "Activo"
        WITHDRAWN = "WITHDRAWN", "Retirado"
        REPLACED = "REPLACED", "Reemplazado"

    case_party = models.ForeignKey(
        CaseParty,
        on_delete=models.PROTECT,
        related_name="lawyer_assignments",
    )

    lawyer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="case_assignments",
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
        db_index=True,
    )

    appointed_at = models.DateField(null=True, blank=True)
    ended_at = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["case_party", "lawyer"],
                condition=models.Q(status="ACTIVE"),
                name="unique_active_lawyer_per_case_party",
            ),
        ]

    def __str__(self):
        return f"{self.lawyer} representa a {self.case_party}"

class CaseMeeting(models.Model):

    case = models.ForeignKey(ArbitrationCase,on_delete=models.CASCADE,related_name="meetings",)
    subject = models.CharField(max_length=255)
    link = models.URLField(max_length=500, blank=True)
    development = models.TextField(blank=True)
    scheduled_at = models.DateTimeField()
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_case_meetings",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["scheduled_at"]

    def __str__(self):
        return f"{self.subject} — {self.scheduled_at:%Y-%m-%d %H:%M}"

class CaseBudget(models.Model):

    class Currency(models.TextChoices):
        PEN = "PEN", "Soles"
        USD = "USD", "Dólares"

    case = models.OneToOneField(
        ArbitrationCase,
        on_delete=models.PROTECT,
        related_name="budget",
    )
    total_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    currency = models.CharField(
        max_length=3,
        choices=Currency.choices,
        default=Currency.PEN,
    )
    initial_budget_file = models.FileField(
        upload_to=case_file_path,
        null=True,
        blank=True,
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_case_budgets",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="updated_case_budgets",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(total_amount__gt=0),
                name="case_budget_amount_positive",
            ),
        ]

    @property
    def total_paid(self):
        result = self.payments.filter(
            status=CasePayment.Status.ACTIVE
        ).aggregate(total=Sum("amount"))

        return result["total"] or Decimal("0.00")

    @property
    def balance(self):
        return self.total_amount - self.total_paid

    def __str__(self):
        return f"Presupuesto de {self.case.code}"

class CasePayment(models.Model):
    class Concept(models.TextChoices):
        ADMINISTRATIVE_EXPENSES = "Gastos administrativos", "Gastos administrativos"
        ARBITRATION_REQUEST_COST = (
            "COSTO DE SOLICITUD DE ARBITRAJES",
            "COSTO DE SOLICITUD DE ARBITRAJES",
        )

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Vigente"
        VOIDED = "VOIDED", "Anulado"

    budget = models.ForeignKey(
        CaseBudget,
        on_delete=models.PROTECT,
        related_name="payments",
    )
    amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    paid_at = models.DateField()
    concept = models.CharField(max_length=255, choices=Concept.choices)
    reference = models.CharField(max_length=100, blank=True, default="")
    receipt = models.FileField(
        upload_to="case_payments/receipts/",
        null=True,
        blank=True,
    )

    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.ACTIVE,
        db_index=True,
    )
    void_reason = models.TextField(blank=True, default="")
    voided_at = models.DateTimeField(null=True, blank=True)
    voided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="voided_case_payments",
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_case_payments",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="updated_case_payments",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-paid_at", "-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount__gt=0),
                name="case_payment_amount_positive",
            ),
        ]

    def __str__(self):
        return f"{self.concept} - {self.amount}"
