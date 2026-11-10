from rest_framework import serializers

from django.utils.timezone import now
from django.conf import settings
from django.db import transaction

from apps.user.models import User
from decimal import Decimal
from .models import Company, GlobalBackup, ProceduralStage, Subject, CaseLocation, CaseNotification, SystemBackup, CaseObservation, Specialty, Procedure, ProcedureFile, ProcedureHistory, ArbitrationCase, CaseSequence, CaseParty, CaseFile, CaseMeeting, CasePartyLawyer, CasePayment, CaseBudget
from .utils import generate_procedure_code
from .services import create_arbitration_case
from django.utils import timezone
from apps.user.serializers import UserSerializer
import os
import logging

logger = logging.getLogger(__name__)

class GlobalBackupSerializer(serializers.ModelSerializer):

    class Meta:
        
        model = GlobalBackup
        fields = "__all__"

class SystemBackupSerializer(serializers.ModelSerializer):

    filename = serializers.ReadOnlyField()
    size_mb = serializers.ReadOnlyField()

    class Meta:
        model = SystemBackup
        fields = (
            "id",
            "filename",
            "backup_type",
            "size",
            "size_mb",
            "created_at"
        )

class CompanySerializer(serializers.ModelSerializer):

    class Meta:
        model = Company
        fields = '__all__'

    def update(self, instance, validated_data):
        # Verificar si hay un nuevo logo
        new_logo = validated_data.get("logo", None)
        if new_logo and instance.logo:
            # Eliminar el logo anterior del sistema de archivos
            old_logo_path = os.path.join(settings.MEDIA_ROOT, str(instance.logo))
            if os.path.exists(old_logo_path):
                os.remove(old_logo_path)

        instance.logo = new_logo if new_logo else instance.logo  # Mantener el anterior si no se envía nuevo
        instance.name = validated_data.get("name", instance.name)
        instance.ruc = validated_data.get("ruc", instance.ruc)
        instance.address = validated_data.get("address", instance.address)

        instance.save()
        return instance

class SubjectSerializer(serializers.ModelSerializer):

    class Meta:
        model = Subject
        fields = '__all__'

class SpecialtySerializer(serializers.ModelSerializer):

    class Meta:
        model = Specialty
        fields = '__all__'

class ProceduralStageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProceduralStage
        fields = "__all__"

class CaseLocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = CaseLocation
        fields = "__all__"

class ProcedureFileSerializer(serializers.ModelSerializer):

    file_name = serializers.CharField(source="filename", read_only=True)
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = ProcedureFile
        fields = ("id", "file_name", "file_url", "created_at")

    def get_file_url(self, obj):
        request = self.context.get("request")
        if request:
            return request.build_absolute_uri(obj.file.url)
        return obj.file.url

class ProcedureListSerializer(serializers.ModelSerializer):

    files = ProcedureFileSerializer(many=True, read_only=True)
 
    class Meta:
        model = Procedure
        fields = '__all__'

    def get_origin_user(self, obj):

        if not obj.created_by:
            return None

        return {
            "id": obj.created_by.id,
            "name": f"{obj.created_by.first_name} {obj.created_by.last_name or ''}".strip()
        }

class ProcedureCreateSerializer(serializers.Serializer):

    # Documento
    subject = serializers.CharField(max_length=255)
    request_detail = serializers.CharField()

    # Remitente
    sender_dni = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=20,
    )
    sender_name = serializers.CharField(max_length=255)
    sender_representante = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=255,
    )
    sender_phone = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=30,
    )
    sender_email = serializers.EmailField(
        required=False,
        allow_blank=True,
    )

    # Adjuntos
    enlaceArchivos = serializers.URLField(
        required=False,
        allow_blank=True,
        allow_null=True,
        max_length=2048,
    )

    modoAdjuntos = serializers.ChoiceField(
        choices=Procedure.AttachmentMode.choices,
        required=True,
    )

    # Tipo de presentación
    is_virtual = serializers.BooleanField(default=True)

    def validate(self, data):
        request = self.context.get("request")

        if request is None:
            raise serializers.ValidationError(
                "No se encontró la solicitud."
            )

        modo = data.get("modoAdjuntos")
        enlace = data.get("enlaceArchivos")
        files = request.FILES.getlist("files")

        if data.get("is_virtual", True):
            if modo == Procedure.AttachmentMode.ENLACE and not enlace:
                raise serializers.ValidationError({
                    "enlaceArchivos": "Debe ingresar el enlace a sus documentos."
                })

            if modo == Procedure.AttachmentMode.ARCHIVOS and not files:
                raise serializers.ValidationError({
                    "files": "Debe adjuntar al menos un archivo."
                })

        return data

    @transaction.atomic
    def create(self, validated_data):

        request = self.context["request"]

        try:

            files = request.FILES.getlist("files")

            is_virtual = validated_data.get("is_virtual",False)

            # Usuario autenticado que registra el trámite.
            user = request.user

            if is_virtual:

               user = User.objects.first()

            else:

               user = request.user

            # 1. Crear el trámite con estado inicial.
            procedure = Procedure.objects.create(
                **validated_data,
                created_by=user,
                code=None,
                status=Procedure.Status.RECEIVED,
            )


            # 2. Guardar los archivos adjuntos
            for file in files:
                ProcedureFile.objects.create(
                    procedure=procedure,
                    file=file,
                    uploaded_by=user,
                    original_name=file.name,
                )

            # 3. Generar y asignar el código
            procedure.code = generate_procedure_code()

            # 4. Guardar ambos campos
            procedure.save(
                update_fields=["code"]
            )
            # 5. Guardar el historial del trámite.
            ProcedureHistory.objects.create(
                procedure=procedure,
                action=ProcedureHistory.Action.RECEIVED,
                previous_status="",
                new_status=procedure.status,
                performed_by=user,
                comment="Trámite recibido y registrado.",
            )

            return procedure

        except serializers.ValidationError:
            raise

        except Exception:
            logger.exception("Error registrando trámite")
            raise serializers.ValidationError({
                "detail": (
                    "Ocurrió un error al registrar el trámite. "
                    "Intente nuevamente."
                )
            })

class CasePartyLawyerSerializer(serializers.ModelSerializer):

    lawyer = UserSerializer(read_only=True)
    status_display = serializers.CharField(
        source="get_status_display",
        read_only=True,
    )

    class Meta:
        model = CasePartyLawyer
        fields = [
            "id",
            "lawyer",
            "status",
            "status_display",
            "appointed_at",
            "ended_at",
            "created_at",
        ]

class CasePartySerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    role_display = serializers.CharField(
        source="get_role_display",
        read_only=True,
    )
    lawyer_assignments = serializers.SerializerMethodField()

    class Meta:
        model = CaseParty
        fields = [
            "id",
            "user",
            "role",
            "role_display",
            "lawyer_assignments",
            "created_at",
        ]

    def get_lawyer_assignments(self, obj):
        active_assignments = obj.lawyer_assignments.filter(
            status=CasePartyLawyer.Status.ACTIVE
        )
        return CasePartyLawyerSerializer(
            active_assignments,
            many=True,
            context=self.context,
        ).data

class CaseFileSerializer(serializers.ModelSerializer):
    
    filename = serializers.ReadOnlyField()

    class Meta:
        model = CaseFile
        fields = [
            "id",
            "case",
            "storage_type",
            "file",
            "external_url",
            "filename",
            "original_name",
            "description",
            "uploaded_by",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "case",
            "filename",
            "uploaded_by",
            "created_at",
        ]

    def validate(self, attrs):
        storage_type = attrs.get(
            "storage_type",
            CaseFile.StorageType.FILE,
        )

        if storage_type == CaseFile.StorageType.FILE:
            uploaded_file = attrs.get("file")
            if not uploaded_file:
                raise serializers.ValidationError({
                    "file": "Debes adjuntar un archivo."
                })

            if uploaded_file.size > 10 * 1024 * 1024:
                raise serializers.ValidationError({
                    "file": "Los archivos mayores a 10 MB deben compartirse mediante un enlace."
                })

            if attrs.get("external_url"):
                raise serializers.ValidationError({
                    "external_url": "No envíes un enlace cuando el tipo es archivo."
                })

        elif storage_type == CaseFile.StorageType.LINK:
            if not attrs.get("external_url"):
                raise serializers.ValidationError({
                    "external_url": "Debes proporcionar el enlace."
                })

            if attrs.get("file"):
                raise serializers.ValidationError({
                    "file": "No adjuntes un archivo cuando el tipo es enlace."
                })

        return attrs

    def create(self, validated_data):
        request = self.context["request"]
        user = (
            request.user
            if request.user.is_authenticated
            else User.objects.order_by("id").first()
        )

        if not user:
            raise serializers.ValidationError({
                "uploaded_by": "No existen usuarios registrados en el sistema."
            })

        uploaded_file = validated_data.get("file")
        if uploaded_file:
            validated_data["original_name"] = uploaded_file.name

        return CaseFile.objects.create(
            case=self.context["case"],
            uploaded_by=user,
            **validated_data,
        )

class CaseMeetingSerializer(serializers.ModelSerializer):
    created_by_name = serializers.CharField(
        source="created_by.get_full_name",
        read_only=True,
    )

    class Meta:
        model = CaseMeeting
        fields = [
            "id",
            "case",
            "subject",
            "link",
            "development",
            "scheduled_at",
            "created_by",
            "created_by_name",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "case",
            "created_by",
            "created_by_name",
            "created_at",
        ]

class CaseObservationSerializer(serializers.ModelSerializer):

    created_by_name = serializers.CharField(
        source="created_by.get_full_name",
        read_only=True,
    )

    class Meta:
        model = CaseObservation
        fields = ["id", "case", "content", "created_by", "created_by_name", "created_at"]
        read_only_fields = ["id", "case", "created_by", "created_by_name", "created_at"]

class CaseNotificationSerializer(serializers.ModelSerializer):
    
    filename = serializers.ReadOnlyField()

    class Meta:
        model = CaseNotification
        fields = [
            "id", "case", "file", "filename", "original_name", "description",
            "uploaded_by", "created_at",
        ]
        read_only_fields = ["id", "case", "filename", "original_name", "uploaded_by", "created_at"]

    def validate_file(self, uploaded_file):
        if not uploaded_file.name.lower().endswith(".pdf"):
            raise serializers.ValidationError("Solo se permiten archivos PDF.")
        if uploaded_file.content_type not in ("application/pdf", "application/x-pdf"):
            raise serializers.ValidationError("El archivo debe tener formato PDF.")
        header = uploaded_file.read(5)
        uploaded_file.seek(0)
        if header != b"%PDF-":
            raise serializers.ValidationError("El contenido del archivo no es un PDF válido.")
        return uploaded_file

    def create(self, validated_data):
        uploaded_file = validated_data["file"]
        validated_data["original_name"] = uploaded_file.name
        return CaseNotification.objects.create(
            case=self.context["case"],
            uploaded_by=self.context["request"].user,
            **validated_data,
        )

class ArbitrationCaseSerializer(serializers.ModelSerializer):
    
    parties = CasePartySerializer(many=True, read_only=True)
    files = CaseFileSerializer(
        source="files_case",
        many=True,
        read_only=True,
    )
    meetings = CaseMeetingSerializer(many=True, read_only=True)
    notifications = CaseNotificationSerializer(many=True, read_only=True)
    observations = CaseObservationSerializer(many=True, read_only=True)

    class Meta:
        model = ArbitrationCase
        fields = [
            "id",
            "code",
            "arbitrator",
            "secretary_arbitrator",
            "subject",
            "process",
            "specialty",
            "procedural_stage",
            "ubicacion",
            "date_of_issue",
            "date_of_due",
            "reason_for_conclusion",
            "controversy_reason",
            "claims",
            "arbitration_agreement",
            "designation_of_arbitrator",
            "amount_in_dispute",
            "status",
            "source_procedure",
            "created_by",
            "parties",
            "files",
            "meetings",
            "notifications",
            "observations",
            "observation"
        ]
        read_only_fields = [
            "id",
            "code",
            "source_procedure",
            "created_by",
            "status",
            "files",
            "meetings",
            "notifications",
            "observations",
        ]
    @transaction.atomic
    def create(self, validated_data):
        user = self.context["request"].user
        year = timezone.localdate().year

        sequence, _ = CaseSequence.objects.get_or_create(
            year=year,
            defaults={"last_number": 0},
        )
        sequence = CaseSequence.objects.select_for_update().get(pk=sequence.pk)
        sequence.last_number += 1
        sequence.save(update_fields=["last_number"])

        return ArbitrationCase.objects.create(
            code=f"{sequence.last_number:03d}-{year}-CSA",
            created_by=user,
            **validated_data,
        )

    def to_representation(self, instance):

        data = super().to_representation(instance)

        data['arbitrator'] = UserSerializer(instance.arbitrator).data
        data['specialty'] = SpecialtySerializer(instance.specialty).data
        data['procedural_stage'] = ProceduralStageSerializer(instance.procedural_stage).data
        data['ubicacion'] = CaseLocationSerializer(instance.ubicacion).data
        data['subject'] = SubjectSerializer(instance.subject).data
        

        return data

class CreateCasePartySerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    password = serializers.CharField(
        write_only=True,
        min_length=8,
        trim_whitespace=False,
    )

    email = serializers.EmailField(
        required=False,
        allow_null=True,
        allow_blank=True,
    )

    first_name = serializers.CharField(max_length=150)
    last_name = serializers.CharField(max_length=150)
    phone = serializers.CharField(
        max_length=30,
        required=False,
        allow_blank=True,
        allow_null=True,
    )

    business_name = serializers.CharField(
        max_length=255,
        required=False,
        allow_blank=True,
        allow_null=True,
    )
    document_type = serializers.CharField(
        max_length=20,
        required=False,
        allow_blank=True,
        allow_null=True,
    )
    document_number = serializers.CharField(
        max_length=30,
        required=False,
        allow_blank=True,
        allow_null=True,
    )
    address = serializers.CharField(
        max_length=255,
        required=False,
        allow_blank=True,
        allow_null=True,
    )

    case_role = serializers.ChoiceField(choices=CaseParty.Role.choices)

    def validate_username(self, value):
        value = value.strip()

        if User.objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError(
                "Ya existe una cuenta con este nombre de usuario."
            )

        return value

    def validate_email(self, value):
        if not value or not value.strip():
            return None

        value = value.strip().lower()

        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError(
                "Ya existe una cuenta con este correo."
            )

        return value

class UpdateCasePartySerializer(serializers.Serializer):

    username = serializers.CharField(max_length=150, required=False)
    password = serializers.CharField(
        write_only=True,
        min_length=8,
        trim_whitespace=False,
        required=False,
    )

    email = serializers.EmailField(
        required=False,
        allow_null=True,
        allow_blank=True,
    )

    first_name = serializers.CharField(max_length=150, required=False)
    last_name = serializers.CharField(max_length=150, required=False)

    phone = serializers.CharField(
        max_length=30,
        required=False,
        allow_blank=True,
        allow_null=True,
    )
    business_name = serializers.CharField(
        max_length=255,
        required=False,
        allow_blank=True,
        allow_null=True,
    )
    document_type = serializers.CharField(
        max_length=20,
        required=False,
        allow_blank=True,
        allow_null=True,
    )
    document_number = serializers.CharField(
        max_length=30,
        required=False,
        allow_blank=True,
        allow_null=True,
    )
    address = serializers.CharField(
        max_length=255,
        required=False,
        allow_blank=True,
        allow_null=True,
    )

    case_role = serializers.ChoiceField(
        choices=CaseParty.Role.choices,
        required=False,
    )

    def validate_username(self, value):
        value = value.strip()
        user = self.instance

        if User.objects.filter(username__iexact=value).exclude(pk=user.pk).exists():
            raise serializers.ValidationError(
                "Ya existe una cuenta con este nombre de usuario."
            )

        return value

    def validate_email(self, value):
        if not value or not value.strip():
            return None

        value = value.strip().lower()
        user = self.instance

        if User.objects.filter(email__iexact=value).exclude(pk=user.pk).exists():
            raise serializers.ValidationError(
                "Ya existe una cuenta con este correo."
            )

        return value

    def update(self, user, validated_data):
        validated_data.pop("case_role", None)

        password = validated_data.pop("password", None)
        if password:
            user.set_password(password)

        for field, value in validated_data.items():
            setattr(user, field, value)

        user.save()
        return user

class AssignLawyerSerializer(serializers.Serializer):
    lawyer = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.filter(
            is_active=True,
            role=User.Role.LAWYER,
        )
    )
    appointed_at = serializers.DateField(required=False, allow_null=True)

    def validate(self, attrs):
        case_party = self.context["case_party"]
        lawyer = attrs["lawyer"]

        already_assigned = CasePartyLawyer.objects.filter(
            case_party=case_party,
            lawyer=lawyer,
            status=CasePartyLawyer.Status.ACTIVE,
        ).exists()

        if already_assigned:
            raise serializers.ValidationError({
                "lawyer": "Este abogado ya está asignado a esta parte."
            })

        return attrs

    def create(self, validated_data):
        return CasePartyLawyer.objects.create(
            case_party=self.context["case_party"],
            lawyer=validated_data["lawyer"],
            appointed_at=validated_data.get("appointed_at"),
        )

class CasePaymentReadSerializer(serializers.ModelSerializer):
    receipt = serializers.FileField(read_only=True)

    class Meta:
        model = CasePayment
        fields = [
            "id",
            "amount",
            "paid_at",
            "concept",
            "reference",
            "receipt",
            "status",
            "void_reason",
            "voided_at",
            "created_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

class CaseBudgetReadSerializer(serializers.ModelSerializer):
    total_paid = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        read_only=True,
    )
    balance = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        read_only=True,
    )
    payments = CasePaymentReadSerializer(many=True, read_only=True)

    class Meta:
        model = CaseBudget
        fields = [
            "id",
            "case",
            "total_amount",
            "currency",
            "total_paid",
            "balance",
            "payments",
            "created_by",
            "updated_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

class CaseBudgetWriteSerializer(serializers.ModelSerializer):
    total_amount = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        min_value=Decimal("0.01"),
    )

    class Meta:
        model = CaseBudget
        fields = ["total_amount", "currency"]

class CasePaymentCreateSerializer(serializers.ModelSerializer):
    amount = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        min_value=Decimal("0.01"),
    )

    class Meta:
        model = CasePayment
        fields = [
            "amount",
            "paid_at",
            "concept",
            "reference",
            "receipt",
        ]

class CasePaymentVoidSerializer(serializers.Serializer):
    reason = serializers.CharField(
        required=True,
        allow_blank=False,
        max_length=1000,
    )

