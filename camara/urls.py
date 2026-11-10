from django.conf import settings
from django.contrib import admin
from django.urls import path, include
from django.conf.urls.static import static

urlpatterns = [
    # Admin (tenant principal)
    path('admin/', admin.site.urls),

    path('api/', include('apps.tramite.urls')),
    path("user/", include("apps.user.urls")),

]

# Archivos media

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
