from django.urls import path
from . import views

urlpatterns = [
    path('dashboard/', views.DashboardSummaryView.as_view(), name='dashboard'),
    path('revenue/', views.RevenueReportView.as_view(), name='revenue-report'),
    path('trips/', views.TripReportView.as_view(), name='trip-report'),
    path('students/', views.StudentReportView.as_view(), name='student-report'),
    # New detailed report endpoints
    path('monthly-trips/', views.MonthlyTripsReportView.as_view(), name='monthly-trips-report'),
    path('bookings/', views.BookingReportView.as_view(), name='bookings-report'),
    path('vehicle-occupancy/', views.VehicleOccupancyReportView.as_view(), name='vehicle-occupancy-report'),
    path('revenue-detail/', views.RevenueDetailReportView.as_view(), name='revenue-detail-report'),
    path('driver-performance/', views.DriverPerformanceReportView.as_view(), name='driver-performance-report'),
]
