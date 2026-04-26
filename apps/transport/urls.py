from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register('routes', views.RouteViewSet, basename='route')
router.register('buses', views.BusViewSet, basename='bus')
router.register('schedules', views.ScheduleViewSet, basename='schedule')
router.register('trips', views.TripViewSet, basename='trip')

urlpatterns = [
    path('', include(router.urls)),
    # Bookings
    path('bookings/', views.MyBookingsView.as_view(), name='my-bookings'),
    path('bookings/create/', views.CreateBookingView.as_view(), name='create-booking'),
    path('bookings/all/', views.AllBookingsView.as_view(), name='all-bookings'),
    path('bookings/board/', views.MarkBoardedView.as_view(), name='mark-boarded'),
    # Driver GPS
    path('location/push/', views.PushBusLocationView.as_view(), name='push-location'),
]
