from rest_framework import generics, permissions, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework import status
from rest_framework.exceptions import PermissionDenied
from django_filters.rest_framework import DjangoFilterBackend
from .serializers import UserSerializer, ModuleSerializer, UserAdminCreateSerializer, UserAdminUpdateSerializer, PositionSerializer
from .services import get_allowed_modules
from .models import User, Position
from .permissions import IsAdminRole

import requests

class PositionViewSet(viewsets.ReadOnlyModelViewSet):

    serializer_class = PositionSerializer
    permission_classes = [IsAuthenticated]

    queryset = Position.objects.filter(
        is_active=True
    ).order_by("category", "order")

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

class MeView(APIView):

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user

        # Módulos permitidos, incluyendo sus padres
        root_modules = get_allowed_modules(user)
        module_tree = ModuleSerializer(
            root_modules,
            many=True
        ).data

        # Datos del usuario
        user_data = UserSerializer(user).data

        # Respuesta combinada
        return Response({
            **user_data,
            "modules": module_tree
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
  