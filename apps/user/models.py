from django.contrib.auth.models import AbstractUser
from django.db import models

from .managers import UserManager

class Position(models.Model):

    class Category(models.TextChoices):
        CHAMBER = "CHAMBER", "Cámara de Comercio"
        COURT = "COURT", "Corte Superior de Arbitraje"

    category = models.CharField(
        "institución",
        max_length=20,
        choices=Category.choices,
        db_index=True
    )

    name = models.CharField(
        "nombre del cargo",
        max_length=150
    )

    code = models.CharField(
        "código",
        max_length=50
    )

    order = models.PositiveIntegerField(default=0)

    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "cargo institucional"
        verbose_name_plural = "cargos institucionales"
        ordering = ["category", "order", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["category", "code"],
                name="unique_position_category_code"
            )
        ]

    def __str__(self):
        return self.name

class User(AbstractUser):

    class Role(models.TextChoices):

        APPLICANT = "APPLICANT", "Solicitante / Parte"
        LAWYER = "LAWYER", "Abogado / Representante"
        ARBITRATOR = "ARBITRATOR", "Árbitro"
        STAFF = "STAFF", "Personal institucional"
        ADMIN = "ADMIN", "Administrador"

    username = models.CharField(
        "nombre de usuario",
        max_length=150,
        unique=True,
        db_index=True
    )

    first_name = models.CharField("nombres", max_length=150)
    last_name = models.CharField("apellidos", max_length=150)
    phone = models.CharField("celular", max_length=30, blank=True, null=True)

    email = models.EmailField(
        "correo electrónico",
        unique=True,
        null=True,
        blank=True
    )

    # Datos personales
    document_type = models.CharField(
        "tipo de documento",
        max_length=20,
        null=True,
        blank=True
    )

    document_number = models.CharField(
        "número de documento",
        max_length=30,
        null=True,
        blank=True
    )

    address = models.CharField(
        "domicilio",
        max_length=255,
        null=True,
        blank=True
    )

    business_name = models.CharField(
        "razón social",
        max_length=255,
        null=True,
        blank=True
    )

    # Datos de representación
    representation = models.CharField(
        max_length=150,
        null=True,
        blank=True
    )

    bar_association = models.CharField(
        max_length=150,
        null=True,
        blank=True
    )

    bar_registration_number = models.CharField(
        max_length=50,
        null=True,
        blank=True
    )

    # Información profesional
    website = models.URLField(max_length=255, null=True, blank=True)
    linkedin = models.URLField(max_length=255, null=True, blank=True)
    profession = models.CharField(max_length=150, null=True, blank=True)
    university = models.CharField(max_length=255, null=True, blank=True)

    sunedu_registered = models.BooleanField(default=False)

    masters_degree = models.CharField(max_length=255, null=True, blank=True)
    masters_university = models.CharField(max_length=255, null=True, blank=True)

    masters_sunedu_registered = models.BooleanField(default=False)

    emission_date = models.DateField(null=True, blank=True)

    # Acceso al sistema
    role = models.CharField(
        "rol de acceso",
        max_length=20,
        choices=Role.choices,
        default=Role.APPLICANT,
        db_index=True
    )

    # Cargo institucional
    position = models.ForeignKey(
        Position,
        on_delete=models.SET_NULL,
        related_name="users",
        null=True,
        blank=True,
        verbose_name="cargo institucional"
    )

    email_verified_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    USERNAME_FIELD = "username"
    REQUIRED_FIELDS = ["first_name", "last_name"]

    objects = UserManager()

    class Meta:
        verbose_name = "usuario"
        verbose_name_plural = "usuarios"
        ordering = ["last_name", "first_name"]

    def __str__(self):
        return f"{self.first_name} {self.last_name}"

    @property
    def is_email_verified(self):
        return self.email_verified_at is not None

class Module(models.Model):

    name = models.CharField(max_length=100)
    path = models.CharField(max_length=100, blank=True, null=True)
    code = models.CharField(max_length=50, unique=True)  # ejemplo: "lecturas", "facturacion"
    icon = models.CharField(max_length=50, blank=True, null=True)  # opcional para el menú
    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        related_name="children",
        blank=True,
        null=True
    )

    order = models.IntegerField(default=0)

    class Meta:
        ordering = ["order", "name"]

    def __str__(self):

        return self.name

class UserPermission(models.Model):

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='permissions')
    module = models.ForeignKey(Module, on_delete=models.CASCADE, related_name='user_permissions')

    class Meta:
        unique_together = ('user', 'module')

    def __str__(self):
        return f"{self.user.username} - {self.module.code}"