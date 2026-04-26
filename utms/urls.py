# from django.contrib import admin
# from django.urls import path, include
# from django.conf import settings
# from django.conf.urls.static import static
# from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView, SpectacularRedocView

# urlpatterns = [
#     path('admin/', admin.site.urls),
#     # API Routes
#     path('api/auth/', include('apps.accounts.urls')),
#     path('api/transport/', include('apps.transport.urls')),
#     path('api/payments/', include('apps.payments.urls')),
#     path('api/reports/', include('apps.reports.urls')),
#     path('api/notifications/', include('apps.notifications.urls')),
#     # API Schema / Docs
#     path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
#     path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
#     path('api/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
# ] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

from django.contrib import admin
from django.urls import path, include

from django.urls import path, include, re_path
from django.conf import settings
from django.conf.urls.static import static
from django.views.static import serve

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('api.urls')),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
