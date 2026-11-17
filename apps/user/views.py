from rest_framework import generics, permissions, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from django_filters.rest_framework import DjangoFilterBackend
from .serializers import UserSerializer, ModuleSerializer, UserAdminCreateSerializer, ChangePasswordSerializer, UserProfileSerializer, UserCaseAccessSerializer, UserMeSerializer, UserModuleAccessSerializer, UserAdminUpdateSerializer, PositionSerializer
from .services import get_allowed_modules
from .models import User, Position, Module, UserModuleAccess
from apps.tramite.models import UserCaseAccess
from .permissions import IsAdminRole
from django.db import transaction
from apps.tramite.emails import send_account_created_email
import requests

class PositionViewSet(viewsets.ReadOnlyModelViewSet):

    serializer_class = PositionSerializer
    permission_classes = [IsAuthenticated]

    queryset = Position.objects.filter(
        is_active=True
    ).order_by("category", "order")

class ModuleViewSet(viewsets.ReadOnlyModelViewSet):

    serializer_class = ModuleSerializer
    queryset = Module.objects.all()

class UserViewSet(viewsets.ModelViewSet):

    queryset = User.objects.all()
    permission_classes = [IsAdminRole]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["role"]

    def get_queryset(self):

        return User.objects.order_by("last_name", "first_name")

    def get_serializer_class(self):

        if self.action == "create":
            return UserAdminCreateSerializer

        if self.action in ("update", "partial_update"):
            return UserAdminUpdateSerializer

        return UserSerializer

    def perform_destroy(self, instance):

        if instance.pk == self.request.user.pk:
            raise PermissionDenied(
                "No puedes eliminar tu propia cuenta."
            )

        instance.delete()

    @action(detail=True, methods=["get", "put"], url_path="modules")
    def modules(self, request, pk=None):

        user = self.get_object()

        if request.method == "GET":

            modules = user.module_accesses.values_list(
                "module_id",
                flat=True
            )

            return Response({
                "user": user.id,
                "modules": list(modules)
            })

        serializer = UserModuleAccessSerializer(
            data=request.data
        )

        serializer.is_valid(raise_exception=True)

        modules = serializer.validated_data["modules"]

        with transaction.atomic():

            user.module_accesses.all().delete()

            UserModuleAccess.objects.bulk_create([
                UserModuleAccess(
                    user=user,
                    module=module
                )
                for module in modules
            ])

        return Response({
            "message": "Módulos actualizados correctamente.",
            "user": user.id,
            "modules": [module.id for module in modules]
        })

    @action(detail=True,methods=["get", "put"],url_path="cases")
    def cases(self, request, pk=None):

        user = self.get_object()

        if request.method == "GET":

            cases = user.case_accesses.values_list(
                "arbitration_case_id",
                flat=True
            )

            return Response({
                "user": user.id,
                "restricted": user.case_access_restricted,
                "cases": list(cases)
            })

        serializer = UserCaseAccessSerializer(
            data=request.data
        )

        serializer.is_valid(raise_exception=True)

        restricted = serializer.validated_data["restricted"]
        cases = serializer.validated_data.get("cases", [])

        with transaction.atomic():

            user.case_access_restricted = restricted

            user.save(update_fields=["case_access_restricted"])

            user.case_accesses.all().delete()

            if restricted:

                UserCaseAccess.objects.bulk_create([
                    UserCaseAccess(
                        user=user,
                        arbitration_case=case
                    )
                    for case in cases
                ])

        return Response({
            "message": "Accesos a expedientes actualizados correctamente.",
            "user": user.id,
            "restricted": restricted,
            "cases": [case.id for case in cases] if restricted else []
        })

    @action(detail=True, methods=["post"], url_path="notify")
    def notify_staff(self, request, pk=None):

        try:

            user = User.objects.get(
                pk=pk,
                role=User.Role.STAFF
            )

        except User.DoesNotExist:

            return Response(
                {"error": "Funcionario no encontrado."},
                status=status.HTTP_404_NOT_FOUND
            )

        # Validar correo
        if not user.email:

            return Response(
                {"error": "El funcionario no tiene correo registrado."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Validar documento
        if not user.document_number:

            return Response(
                {"error": "El funcionario no tiene número de documento registrado."},
                status=status.HTTP_400_BAD_REQUEST
            )

        temporary_password = user.document_number

        try:

            # Enviar correo HTML
            send_account_created_email(
                user,
                temporary_password
            )

            return Response({
                "message": "Credenciales enviadas correctamente.",
                "username": user.username
            })

        except Exception:

            return Response(
                {"error": "No se pudo enviar el correo de credenciales."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class MeView(APIView):

    permission_classes = [permissions.IsAuthenticated]

    def get_response_data(self, request):

        user = request.user

        root_modules = get_allowed_modules(user)

        module_tree = ModuleSerializer(
            root_modules,
            many=True,
            context={"request": request}
        ).data

        user_data = UserProfileSerializer(user).data

        return {
            **user_data,
            "modules": module_tree
        }

    def get(self, request):

        return Response(
            self.get_response_data(request)
        )

    def patch(self, request):

        serializer = UserProfileSerializer(
            request.user,
            data=request.data,
            partial=True
        )

        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response({
            "message": "Perfil actualizado correctamente.",
            "user": self.get_response_data(request)
        })

class ChangePasswordView(APIView):

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):

        serializer = ChangePasswordSerializer(
            data=request.data,
            context={"request": request}
        )

        serializer.is_valid(raise_exception=True)

        user = request.user
        user.set_password(serializer.validated_data["new_password"])
        user.save(update_fields=["password"])

        return Response({
            "message": "Contraseña actualizada correctamente."
        })

class LogoutView(APIView):

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):

        refresh_token = request.data.get("refresh")

        if not refresh_token:

            return Response({"detail": "Se requiere el refresh token."}, status=400)
        
        try:

            RefreshToken(refresh_token).blacklist()

        except Exception:

            return Response({"detail": "Refresh token inválido."}, status=400)
        
        return Response(status=205)

class RucApiView(APIView):

    authentication_classes = [] 
    permission_classes = []    

    def get(self, request, number):

        # Construcción del endpoint y encabezados
        url = f"https://apifoxnube.com/api/ruc/{number}"
        token = "JDuaRQyRDjiD6a6NpMXdRHoKiOfsUxksnbFRNNK0"
        headers = {"Authorization": f"Bearer {token}"}

        try:
            # Solicitud al servicio externo
            response = requests.get(url, headers=headers, timeout=10)

            # Validar respuesta
            if response.status_code == 200:
                return Response(response.json())
            else:
                return Response(
                    {"error": f"Error al consultar el servicio externo. details {response.json()}"}, status=response.status_code,
                )
        except requests.RequestException as e:
            # Manejo de excepciones en caso de error de conexión o tiempo de espera
            return Response(
                {"error": f"Error al conectar con el servicio externo. details {str(e)}"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        
class DniApiView(APIView):

    authentication_classes = [] 
    permission_classes = []    
    
    def get(self, request, number):

        # Construcción del endpoint y encabezados
        url = f"https://apifoxnube.com/api/dni/{number}"
        token = "JDuaRQyRDjiD6a6NpMXdRHoKiOfsUxksnbFRNNK0"
        headers = {"Authorization": f"Bearer {token}"}

        try:
            # Solicitud al servicio externo
            response = requests.get(url, headers=headers, timeout=10)

            # Validar respuesta
            if response.status_code == 200:
                return Response(response.json())
            else:
                return Response(
                    response.json(), status=response.status_code,
                )
        except requests.RequestException as e:
            # Manejo de excepciones en caso de error de conexión o tiempo de espera
            return Response(
                {"error": f"Error al conectar con el servicio externo. details {str(e)}"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
  