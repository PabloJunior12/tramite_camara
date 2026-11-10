from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from .views import LogoutView, MeView, RucApiView, DniApiView, UserViewSet, PositionViewSet
from rest_framework.routers import DefaultRouter

router = DefaultRouter()
router.register("users", UserViewSet, basename="user")
router.register("positions", PositionViewSet, basename="position")

urlpatterns = [
    
    path("token/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("login/", TokenObtainPairView.as_view(), name="login"),
    path("me/", MeView.as_view(), name="me"),

    path('ruc/<str:number>', RucApiView.as_view(), name='user-ruc'),
    path('dni/<str:number>', DniApiView.as_view(), name='user-dni'),

] + router.urls
