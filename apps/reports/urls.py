from django.urls import path
from . import views

urlpatterns = [
    path('dashboard/', views.DashboardSummaryView.as_view(), name='dashboard'),
    path('revenue/', views.RevenueReportView.as_view(), name='revenue-report'),
    path('trips/', views.TripReportView.as_view(), name='trip-report'),
    path('students/', views.StudentReportView.as_view(), name='student-report'),
]
