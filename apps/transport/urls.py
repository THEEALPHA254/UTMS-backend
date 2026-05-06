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
    # Student bookings
    path('bookings/', views.MyBookingsView.as_view(), name='my-bookings'),
    path('bookings/create/', views.CreateBookingView.as_view(), name='create-booking'),
    # Admin/staff bookings
    path('bookings/all/', views.AllBookingsView.as_view(), name='all-bookings'),
    # Driver: scan QR to board student
    path('bookings/board/', views.MarkBoardedView.as_view(), name='mark-boarded'),
    # Driver: list passengers for a trip  (?trip=<id>)
    path('bookings/passengers/', views.TripPassengersView.as_view(), name='trip-passengers'),
    # Driver: push GPS
    path('location/push/', views.PushBusLocationView.as_view(), name='push-location'),
]
