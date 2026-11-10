from rest_framework import status, viewsets, generics, filters, mixins
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.views import APIView
from django.conf import settings
from rest_framework.permissions import IsAuthenticated,AllowAny
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from django.db import transaction
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.db.models import (
    DecimalField,
    ExpressionWrapper,
    F,
    Q,
    Sum,
    Value,
)
from django.db.models.functions import TruncMonth, Coalesce
from .models import Company, Procedure, ArbitrationCase, CaseSequence, Subject, CaseParty, CaseFile, CaseMeeting, CasePartyLawyer, CaseBudget, CasePayment, Specialty, ProceduralStage, CaseLocation, CaseObservation, CaseNotification
from .serializers import CompanySerializer, ProcedureCreateSerializer, UpdateCasePartySerializer, SubjectSerializer, ProcedureListSerializer, CaseMeetingSerializer, ArbitrationCaseSerializer, CaseFileSerializer, CreateCasePartySerializer, CasePartyLawyerSerializer, AssignLawyerSerializer, CasePaymentVoidSerializer, CaseBudgetReadSerializer, CaseBudgetWriteSerializer, CasePaymentReadSerializer, CasePaymentCreateSerializer, SpecialtySerializer, ProceduralStageSerializer, CaseLocationSerializer, CaseObservationSerializer, CaseNotificationSerializer
from .utils import ProcedureFilter
from .services import create_arbitration_case
from django.core.exceptions import ValidationError
from django_filters.rest_framework import DjangoFilterBackend
from django.shortcuts import get_object_or_404
User = get_user_model()
from datetime import date
from collections import defaultdict
from decimal import Decimal
from django.utils.dateparse import parse_date
from django.template.loader import render_to_string
from django.http import HttpResponse
from weasyprint import HTML
from .emails import send_procedure_received_email, send_procedure_rejected_email, send_procedure_approved_email

ZERO = Value(
    Decimal("0.00"),
    output_field=DecimalField(max_digits=14, decimal_places=2),
)

class CustomPagination(PageNumberPagination):

    page_size = 5  # Número de registros por página
    page_size_query_param = 'page_size'  # Permite cambiar el tamaño desde la URL
    max_page_size = 100  # Tamaño máximo permitido

class CompanyViewSet(viewsets.ModelViewSet):

    authentication_classes = [] 
    permission_classes = []    
    queryset = Company.objects.all()
    serializer_class = CompanySerializer

class SpecialtyViewSet(viewsets.ModelViewSet):

    queryset = Specialty.objects.all()
    serializer_class = SpecialtySerializer

class SubjectViewSet(viewsets.ModelViewSet):

    queryset = Subject.objects.all()
    serializer_class = SubjectSerializer

class ProceduralStageViewSet(viewsets.ModelViewSet):

    queryset = ProceduralStage.objects.all()
    serializer_class = ProceduralStageSerializer

class CaseLocationViewSet(viewsets.ModelViewSet):

    queryset = CaseLocation.objects.all()
    serializer_class = CaseLocationSerializer

class ProcedureViewSet(viewsets.ModelViewSet):
    
    queryset = Procedure.objects.prefetch_related("files").order_by("-created_at")
    pagination_class = CustomPagination
    filter_backends = [DjangoFilterBackend]
    filterset_class = ProcedureFilter

    def get_serializer_class(self):
        if self.action == "create":
            return ProcedureCreateSerializer
        return ProcedureListSerializer

    def get_serializer_context(self):
        context = super().get_serializer_context()
        return context

    def get_permissions(self):
        if self.action == "create":
            return [AllowAny()]

        return super().get_permissions()

    def create(self, request, *args, **kwargs):

        serializer = self.get_serializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        procedure = serializer.save()

        email_sent = send_procedure_received_email(procedure)

        return Response(
            {
                "message": "Trámite registrado exitosamente.",
                "id": procedure.id,
                "code": procedure.code,
                "status": procedure.status,
                "email_sent": email_sent,
            },
            status=status.HTTP_201_CREATED,
        )
            
    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated])
    def reject(self, request, pk=None):
        procedure = self.get_object()
        reason = request.data.get("reason", "").strip()

        if not reason:
            raise ValidationError({
                "reason": "Indica el motivo del rechazo."
            })

        procedure.status = Procedure.Status.REJECTED
        procedure.rejection_reason = reason
        procedure.review_observation = None
        procedure.reviewed_at = timezone.now()
        procedure.reviewed_by = request.user
        procedure.save()

        email_sent = send_procedure_rejected_email(procedure)

        return Response(
            {
                "message": (
                    "Trámite rechazado y correo enviado al usuario."
                    if email_sent
                    else "Trámite rechazado, pero no se pudo enviar el correo."
                ),
                "status": procedure.status,
                "reason": procedure.rejection_reason,
                "email_sent": email_sent,
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated])
    def approve(self, request, pk=None):
        procedure = self.get_object()

        allowed_statuses = [
            Procedure.Status.RECEIVED,
            Procedure.Status.UNDER_REVIEW,
            Procedure.Status.OBSERVED,
        ]

        if procedure.status not in allowed_statuses:
            return Response(
                {
                    "error": (
                        "Este trámite no puede aprobarse "
                        "desde su estado actual."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        procedure.status = Procedure.Status.APPROVED
        procedure.reviewed_at = timezone.now()
        procedure.reviewed_by = request.user
        procedure.save(
            update_fields=[
                "status",
                "reviewed_at",
                "reviewed_by",
            ]
        )

        email_sent = send_procedure_approved_email(procedure)

        return Response({
            "message": (
                "Trámite aprobado y correo enviado al usuario."
                if email_sent
                else "Trámite aprobado, pero no se pudo enviar el correo."
            ),
            "status": procedure.status,
            "code": procedure.code,
            "email_sent": email_sent,
        })

class ArbitrationCaseViewSet(viewsets.ModelViewSet):
 
    serializer_class = ArbitrationCaseSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["code"]

    def get_authenticators(self):
        if self.request.method == "PATCH":
            return []
        return super().get_authenticators()

    def get_permissions(self):
        if self.request.method == "PATCH":
            return [AllowAny()]
        return super().get_permissions()

    def get_queryset(self):
        queryset = (
            ArbitrationCase.objects
            .select_related("arbitrator", "created_by")
            .prefetch_related(
                "parties__user",
                "parties__lawyer_assignments__lawyer",
                "files_case",
                "meetings",
            )
        )

        user = self.request.user
        if user.is_authenticated and user.role == User.Role.APPLICANT:
            queryset = queryset.filter(parties__user=user).distinct()

        return queryset

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)

        headers = self.get_success_headers(serializer.data)
        return Response(
            serializer.data,
            status=status.HTTP_201_CREATED,
            headers=headers,
        )

    def update(self, request, *args, **kwargs):

        partial = kwargs.pop("partial", False)
        instance = self.get_object()

        serializer = self.get_serializer(
            instance,
            data=request.data,
            partial=partial,
        )
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)

        return Response(serializer.data)

    @action(
        detail=False,
        methods=["get"],
        url_path=r"locate/(?P<code>[^/.]+)",
        url_name="locate",
        permission_classes=[AllowAny],
        authentication_classes=[],
    )
    def locate(self, request, code=None):
        try:
            expediente = self.get_queryset().get(code=code)
        except ArbitrationCase.DoesNotExist:
            return Response(
                {
                    "detail": "No se encontró un expediente con ese código."
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = self.get_serializer(expediente)

        return Response(
            serializer.data,
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["post"], url_path="close")
    def close_case(self, request, pk=None):
        case = self.get_object()

        if case.status == ArbitrationCase.Status.CLOSED:
            raise ValidationError({"detail": "El expediente ya está cerrado."})

        reason = request.data.get("closing_reason", "").strip()

        if not reason:
            raise ValidationError({
                "closing_reason": "Este campo es obligatorio para cerrar el expediente."
            })

        case.status = ArbitrationCase.Status.CLOSED
        case.closed_at = timezone.now()
        case.closing_reason = reason
        case.save(update_fields=[
            "status",
            "closed_at",
            "closing_reason",
        ])

        return Response(self.get_serializer(case).data)

    @action(detail=False, methods=["get"], url_path="code-preview")
    def code_preview(self, request):
        year = timezone.localdate().year

        sequence = CaseSequence.objects.filter(
            year=year
        ).values_list("last_number", flat=True).first()

        next_number = (sequence or 0) + 1

        return Response({
            "code": f"{next_number:03d}-{year}-CSA"
        })

    @action(detail=True, methods=["get"], url_path="access-pdf")
    def access_pdf(self, request, pk=None):
        case = self.get_object()

        def get_participants(role):
            parties = (
                case.parties
                .filter(role=role)
                .select_related("user")
                .order_by("user__email")
            )

            return [
                {
                    "name": party.user.get_full_name().strip() or party.user.email,
                    "role": party.get_role_display(),
                    "username": party.user.email,
                    "email": party.user.email,
                }
                for party in parties
            ]

        html_content = render_to_string(
            "cases/access_pdf.html",
            {
                "case": case,
                "respondents": get_participants(
                    CaseParty.Role.RESPONDENT
                ),
                "claimants": get_participants(
                    CaseParty.Role.CLAIMANT
                ),
                "initial_password": "12345678",
                "system_url": "http://localhost:4200/",
            },
        )

        pdf_file = HTML(
            string=html_content,
            base_url=request.build_absolute_uri("/"),
        ).write_pdf()

        response = HttpResponse(pdf_file, content_type="application/pdf")
        response["Content-Disposition"] = (
            f'inline; filename="accesos_{case.code}.pdf"'
        )
        return response

class ArbitrationCaseFileViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):

    serializer_class = CaseFileSerializer
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_queryset(self):
        return CaseFile.objects.filter(
            case_id=self.kwargs["case_pk"]
        ).select_related("uploaded_by")

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["case"] = get_object_or_404(
            ArbitrationCase,
            pk=self.kwargs["case_pk"],
        )
        return context

    def create(self, request, *args, **kwargs):
        case = get_object_or_404(
            ArbitrationCase,
            pk=self.kwargs["case_pk"],
        )

        # Un enlace llega como JSON.
        if request.data.get("storage_type") == CaseFile.StorageType.LINK:
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            instance = serializer.save()

            return Response(
                self.get_serializer(instance).data,
                status=status.HTTP_201_CREATED,
            )

        # Los archivos llegan como multipart/form-data.
        files = request.FILES.getlist("files")

        if not files:
            return Response(
                {"files": "Selecciona al menos un archivo."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        created = []

        for uploaded_file in files:
            serializer = self.get_serializer(data={
                "storage_type": CaseFile.StorageType.FILE,
                "file": uploaded_file,
                "description": request.data.get("description", ""),
            })
            serializer.is_valid(raise_exception=True)
            created.append(serializer.save())

        return Response(
            self.get_serializer(created, many=True).data,
            status=status.HTTP_201_CREATED,
        )

class ArbitrationCaseMeetingViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = CaseMeetingSerializer

    def get_queryset(self):
        return CaseMeeting.objects.filter(
            case_id=self.kwargs["case_pk"]
        ).select_related("created_by")

    def perform_create(self, serializer):
        case = get_object_or_404(
            ArbitrationCase,
            pk=self.kwargs["case_pk"],
        )
        serializer.save(case=case, created_by=self.request.user)


class ArbitrationCaseObservationViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = CaseObservationSerializer

    def get_queryset(self):
        return CaseObservation.objects.filter(
            case_id=self.kwargs["case_pk"]
        ).select_related("created_by")

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["case"] = get_object_or_404(ArbitrationCase, pk=self.kwargs["case_pk"])
        return context

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        case = get_object_or_404(ArbitrationCase, pk=self.kwargs["case_pk"])
        is_many = isinstance(request.data, list)
        serializer = self.get_serializer(data=request.data, many=is_many)
        serializer.is_valid(raise_exception=True)
        observations = serializer.save(case=case, created_by=request.user)
        return Response(
            self.get_serializer(observations, many=is_many).data,
            status=status.HTTP_201_CREATED,
        )

class ArbitrationCaseNotificationViewSet(
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = CaseNotificationSerializer
    parser_classes = [MultiPartParser, FormParser]

    def get_queryset(self):
        return CaseNotification.objects.filter(
            case_id=self.kwargs["case_pk"]
        ).select_related("uploaded_by")

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["case"] = get_object_or_404(ArbitrationCase, pk=self.kwargs["case_pk"])
        return context

    def create(self, request, *args, **kwargs):
        files = request.FILES.getlist("files") or request.FILES.getlist("file")
        if not files:
            return Response({"files": "Adjunta al menos un archivo PDF."}, status=status.HTTP_400_BAD_REQUEST)

        context = self.get_serializer_context()
        serializers_to_save = [
            self.get_serializer(data={"file": uploaded_file, "description": request.data.get("description", "")}, context=context)
            for uploaded_file in files
        ]
        for serializer in serializers_to_save:
            serializer.is_valid(raise_exception=True)

        created = [serializer.save() for serializer in serializers_to_save]
        return Response(self.get_serializer(created, many=True, context=context).data, status=status.HTTP_201_CREATED)
   
        
class CreateCasePartyView(APIView):
        
        def post(self, request, case_id):
            case = get_object_or_404(ArbitrationCase, pk=case_id)

            serializer = CreateCasePartySerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            data = serializer.validated_data

            with transaction.atomic():
                user = User.objects.create_user(
                    username=data["username"],
                    password=data["password"],
                    email=data.get("email") or None,
                    first_name=data["first_name"],
                    last_name=data["last_name"],
                    phone=data.get("phone") or "",
                    business_name=data.get("business_name") or "",
                    document_type=data.get("document_type") or "",
                    document_number=data.get("document_number") or "",
                    address=data.get("address") or "",
                    role=User.Role.APPLICANT,
                )

                case_party = CaseParty.objects.create(
                    case=case,
                    user=user,
                    role=data["case_role"],
                )

            return Response(
                {
                    "id": case_party.id,
                    "case": case.id,
                    "case_code": case.code,
                    "user": {
                        "id": user.id,
                        "username": user.username,
                        "email": user.email,
                        "first_name": user.first_name,
                        "last_name": user.last_name,
                        "business_name": user.business_name,
                        "document_type": user.document_type,
                        "document_number": user.document_number,
                    },
                    "role": case_party.role,
                },
                status=status.HTTP_201_CREATED,
            )

class UpdateCasePartyView(APIView):

    def patch(self, request, case_id, case_party_id):

        case_party = get_object_or_404(
            CaseParty.objects.select_related("user"),
            pk=case_party_id,
            case_id=case_id,
        )

        serializer = UpdateCasePartySerializer(
            case_party.user,
            data=request.data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)

        with transaction.atomic():
            user = serializer.save()

            if "case_role" in request.data:
                case_party.role = request.data["case_role"]
                case_party.save(update_fields=["role"])

        return Response({
            "id": case_party.id,
            "case": case_party.case_id,
            "user": {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "first_name": user.first_name,
                "last_name": user.last_name,
            },
            "role": case_party.role,
        })

class DeleteCasePartyView(APIView):

    def delete(self, request, case_id, case_party_id):

        case_party = get_object_or_404(CaseParty.objects.select_related("user"), pk=case_party_id, case_id=case_id)
        user = case_party.user

        with transaction.atomic():

            case_party.delete()

            if not user.case_participations.exists():
               user.delete()

        return Response(status=status.HTTP_204_NO_CONTENT)
    
class CasePartyLawyerListCreateAPIView(APIView):

    def get_case_party(self, case_party_id):
        return get_object_or_404(
            CaseParty.objects.select_related("case", "user"),
            pk=case_party_id,
        )

    def get(self, request, case_party_id):
        case_party = self.get_case_party(case_party_id)

        assignments = (
            CasePartyLawyer.objects
            .filter(case_party=case_party)
            .select_related("lawyer", "case_party")
            .order_by("-created_at")
        )

        return Response(
            CasePartyLawyerSerializer(assignments, many=True).data
        )

    def post(self, request, case_party_id):

        case_party = self.get_case_party(case_party_id)

        serializer = AssignLawyerSerializer(
            data=request.data,
            context={"case_party": case_party},
        )
        serializer.is_valid(raise_exception=True)

        assignment = serializer.save()

        return Response(
            CasePartyLawyerSerializer(assignment).data,
            status=status.HTTP_201_CREATED,
        )

    def delete(self, request, case_party_id, assignment_id):
        case_party = self.get_case_party(case_party_id)
        assignment = get_object_or_404(
            CasePartyLawyer,
            pk=assignment_id,
            case_party=case_party,
            status=CasePartyLawyer.Status.ACTIVE,
        )
        assignment.status = CasePartyLawyer.Status.WITHDRAWN
        assignment.ended_at = timezone.localdate()
        assignment.save(update_fields=["status", "ended_at"])

        return Response(CasePartyLawyerSerializer(assignment).data)

class CaseBudgetAPIView(APIView):

    def get(self, request, case_id):

        get_object_or_404(ArbitrationCase, pk=case_id)

        budget = (
            CaseBudget.objects
            .filter(case_id=case_id)
            .prefetch_related("payments")
            .first()
        )

        if budget is None:
            return Response(
                {"detail": "Este expediente aún no tiene presupuesto."},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(
            CaseBudgetReadSerializer(
                budget,
                context={"request": request},
            ).data
        )

    def post(self, request, case_id):
        serializer = CaseBudgetWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if not serializer.validated_data.get("initial_budget_file"):
            raise ValidationError({
                "initial_budget_file": "Adjunta el PDF del presupuesto inicial."
            })

        with transaction.atomic():
            # Serializa la creación de presupuesto para este expediente.
            case = get_object_or_404(
                ArbitrationCase.objects.select_for_update(),
                pk=case_id,
            )

            if CaseBudget.objects.filter(case=case).exists():
                raise ValidationError({
                    "detail": "El expediente ya tiene un presupuesto."
                })

            budget = serializer.save(
                case=case,
                created_by=request.user,
            )

        return Response(
            CaseBudgetReadSerializer(
                budget,
                context={"request": request},
            ).data,
            status=status.HTTP_201_CREATED,
        )

    def patch(self, request, case_id):
        serializer = CaseBudgetWriteSerializer(
            data=request.data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)

        with transaction.atomic():
            budget = get_object_or_404(
                CaseBudget.objects.select_for_update(),
                case_id=case_id,
            )

            total_paid = budget.total_paid
            new_amount = serializer.validated_data.get(
                "total_amount",
                budget.total_amount,
            )
            new_currency = serializer.validated_data.get(
                "currency",
                budget.currency,
            )

            if new_amount < total_paid:
                raise ValidationError({
                    "total_amount": (
                        "El presupuesto no puede ser menor que el monto "
                        "ya pagado."
                    )
                })

            if new_currency != budget.currency and total_paid > 0:
                raise ValidationError({
                    "currency": (
                        "No se puede cambiar la moneda después de registrar "
                        "pagos."
                    )
                })

            for field, value in serializer.validated_data.items():
                setattr(budget, field, value)

            budget.updated_by = request.user
            budget.save()

        budget = CaseBudget.objects.prefetch_related("payments").get(pk=budget.pk)

        return Response(
            CaseBudgetReadSerializer(
                budget,
                context={"request": request},
            ).data
        )

class CasePaymentListCreateAPIView(APIView):
   
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get_budget(self, case_id):
        return get_object_or_404(
            CaseBudget.objects.select_related("case"),
            case_id=case_id,
        )

    def get(self, request, case_id):
        budget = self.get_budget(case_id)
        payments = budget.payments.all()

        return Response(
            CasePaymentReadSerializer(
                payments,
                many=True,
                context={"request": request},
            ).data
        )

    def post(self, request, case_id):
        serializer = CasePaymentCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        with transaction.atomic():
            budget = get_object_or_404(
                CaseBudget.objects.select_for_update(),
                case_id=case_id,
            )

            amount = serializer.validated_data["amount"]
            balance = budget.balance

            if amount > balance:
                raise ValidationError({
                    "amount": (
                        f"El pago supera el saldo disponible "
                        f"({balance} {budget.currency})."
                    )
                })

            payment = serializer.save(
                budget=budget,
                created_by=request.user,
            )

        return Response(
            CasePaymentReadSerializer(
                payment,
                context={"request": request},
            ).data,
            status=status.HTTP_201_CREATED,
        )

class CasePaymentVoidAPIView(APIView):

    def post(self, request, case_id, payment_id):
        serializer = CasePaymentVoidSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        with transaction.atomic():
            payment = get_object_or_404(
                CasePayment.objects.select_for_update(),
                pk=payment_id,
                budget__case_id=case_id,
            )

            if payment.status == CasePayment.Status.VOIDED:
                raise ValidationError({
                    "detail": "Este pago ya está anulado."
                })

            payment.status = CasePayment.Status.VOIDED
            payment.void_reason = serializer.validated_data["reason"]
            payment.voided_at = timezone.now()
            payment.voided_by = request.user
            payment.updated_by = request.user
            payment.save(update_fields=[
                "status",
                "void_reason",
                "voided_at",
                "voided_by",
                "updated_by",
                "updated_at",
            ])

        return Response(
            CasePaymentReadSerializer(
                payment,
                context={"request": request},
            ).data
        )

class PaymentsReportPDFView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request):
        payments = (
            CasePayment.objects
            .select_related(
                "budget",
                "budget__case",
                "created_by",
                "voided_by",
            )
            .order_by("-paid_at", "-created_at")
        )

        # Filtro por expediente
        code = request.query_params.get("code")
        if code:
            payments = payments.filter(
                budget__case__code__icontains=code
            )

        # Filtro por fechas
        date_from = request.query_params.get("date_from")
        date_to = request.query_params.get("date_to")

        if date_from:
            parsed_from = parse_date(date_from)
            if not parsed_from:
                raise ValidationError({
                    "date_from": "Usa el formato YYYY-MM-DD."
                })
            payments = payments.filter(paid_at__gte=parsed_from)

        if date_to:
            parsed_to = parse_date(date_to)
            if not parsed_to:
                raise ValidationError({
                    "date_to": "Usa el formato YYYY-MM-DD."
                })
            payments = payments.filter(paid_at__lte=parsed_to)

        # Filtro por estado
        status_filter = request.query_params.get("status")
        if status_filter:
            valid_statuses = CasePayment.Status.values
            if status_filter not in valid_statuses:
                raise ValidationError({
                    "status": "Estado de pago no válido."
                })
            payments = payments.filter(status=status_filter)

        # Totales separados por moneda
        totals = defaultdict(lambda: {
            "budget": Decimal("0.00"),
            "paid": Decimal("0.00"),
            "voided": Decimal("0.00"),
            "balance": Decimal("0.00"),
        })

        # Obtener presupuestos relacionados con los pagos filtrados.
        budgets = {
            budget.id: budget
            for budget in (
                payment.budget for payment in payments
            )
        }

        for budget in budgets.values():
            currency = budget.currency
            totals[currency]["budget"] += budget.total_amount
            totals[currency]["paid"] += budget.total_paid
            totals[currency]["balance"] += budget.balance

        for payment in payments:
            if payment.status == CasePayment.Status.VOIDED:
                totals[payment.budget.currency]["voided"] += payment.amount

        context = {
            "payments": payments,
            "totals": dict(totals),
            "date_from": date_from or "",
            "date_to": date_to or "",
            "code": code or "",
            "status_filter": status_filter or "",
            "generated_at": timezone.localtime(),
        }

        html_string = render_to_string("reports/payments_report.html",
            context,
            request=request,
        )

        pdf = HTML(
            string=html_string,
            base_url=request.build_absolute_uri("/"),
        ).write_pdf()

        response = HttpResponse(
            pdf,
            content_type="application/pdf",
        )
        response["Content-Disposition"] = (
            'inline; filename="reporte_pagos.pdf"'
        )
        return response

class AccountingDashboardView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request):

        # Solo presupuestos en soles
        budgets = (
            CaseBudget.objects
            .filter(currency=CaseBudget.Currency.PEN)
            .select_related("case")
            .annotate(
                paid_total=Coalesce(
                    Sum(
                        "payments__amount",
                        filter=Q(
                            payments__status=CasePayment.Status.ACTIVE
                        ),
                    ),
                    Decimal("0.00"),
                    output_field=DecimalField(
                        max_digits=14,
                        decimal_places=2,
                    ),
                )
            )
            .annotate(
                raw_balance=ExpressionWrapper(
                    F("total_amount") - F("paid_total"),
                    output_field=DecimalField(
                        max_digits=14,
                        decimal_places=2,
                    ),
                )
            )
        )

        # RESUMEN FINANCIERO
        total_collected = (
            budgets.aggregate(
                total=Sum("paid_total")
            )["total"] or Decimal("0.00")
        )

        total_pending = (
            budgets.filter(raw_balance__gt=0)
            .aggregate(
                total=Sum("raw_balance")
            )["total"] or Decimal("0.00")
        )

        currency_totals = [{
            "currency": "PEN",
            "currency_label": "Soles",
            "total_collected": str(total_collected),
            "total_pending": str(total_pending),
        }]

        # SALDOS PENDIENTES POR EXPEDIENTE
        pending_budgets = (
            budgets
            .filter(raw_balance__gt=0)
            .order_by("-raw_balance", "-case__created_at")
        )

        cases = [
            {
                "case_id": budget.case_id,
                "case_code": budget.case.code,
                "subject": budget.case.subject.name,
                "pending_amount": str(budget.raw_balance),
                "currency": "PEN",
            }
            for budget in pending_budgets
        ]

        pending_by_currency = [{
            "currency": "PEN",
            "currency_label": "Soles",
            "cases": cases,
        }]

        # TOP 10 EXPEDIENTES CON MAYOR DEUDA
        top_debts = (
            budgets
            .filter(raw_balance__gt=0)
            .order_by("-raw_balance", "-case__created_at")[:10]
        )

        highest_debt_cases = [
            {
                "case_id": budget.case_id,
                "case_code": budget.case.code,
                "subject": budget.case.subject.name,
                "currency": "PEN",
                "budget_total": str(budget.total_amount),
                "paid_total": str(budget.paid_total),
                "pending_amount": str(budget.raw_balance),
                "created_at": budget.case.created_at.isoformat(),
            }
            for budget in top_debts
        ]

        return Response({
            "currency_totals": currency_totals,
            "pending_by_currency": pending_by_currency,
            "highest_debt_cases": highest_debt_cases,
        })
