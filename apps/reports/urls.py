from django.urls import path
from . import views

urlpatterns = [
    path('dashboard/', views.DashboardSummaryView.as_view(), name='dashboard-summary'),
    path('revenue/daily/', views.RevenueChartView.as_view(), name='revenue-daily'),
    path('revenue/monthly/', views.MonthlyStatsView.as_view(), name='monthly-stats'),
    path('routes/popularity/', views.RoutePopularityView.as_view(), name='route-popularity'),
    path('students/usage/', views.StudentUsageReportView.as_view(), name='student-usage'),
    path('payments/', views.PaymentReportView.as_view(), name='payment-report'),
]
