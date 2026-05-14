from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt import views as jwt_views
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView, SpectacularRedocView
from apps.transport.views import RouteViewSet, BusViewSet, ScheduleViewSet, TripViewSet

router = DefaultRouter()
router.register('routes', RouteViewSet, basename='route')
router.register('buses', BusViewSet, basename='bus')
router.register('schedules', ScheduleViewSet, basename='schedule')
router.register('trips', TripViewSet, basename='trip')

# app_name = "api"
urlpatterns = [
    path('', include(router.urls)),
    path("auth/", include("apps.accounts.urls")),
    path('transport/', include('apps.transport.urls')),
    path('payments/', include('apps.payments.urls')),
    path('reports/', include('apps.reports.urls')),
    path('notifications/', include('apps.notifications.urls')),
    # API Schema / Docs
    path('schema/', SpectacularAPIView.as_view(), name='schema'),
    path('docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
   
]