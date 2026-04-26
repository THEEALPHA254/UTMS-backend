from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import permissions
from django.db.models import Sum, Count, Q
from django.db.models.functions import TruncDate, TruncMonth
from django.http import HttpResponse
from django.utils import timezone
from datetime import timedelta
import csv
import json

from apps.transport.models import Booking, Trip, Route
from apps.payments.models import Transaction
from apps.accounts.models import StudentProfile, User


class IsAdminOrStaff(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.role in ['admin', 'staff']


class DashboardSummaryView(APIView):
    """High-level KPIs for the admin dashboard."""
    permission_classes = [IsAdminOrStaff]

    def get(self, request):
        today = timezone.now().date()
        month_start = today.replace(day=1)

        total_students = StudentProfile.objects.count()
        active_students = StudentProfile.objects.filter(transport_status='active').count()

        total_revenue = Transaction.objects.filter(
            status='success', transaction_type='wallet_topup'
        ).aggregate(total=Sum('amount'))['total'] or 0

        monthly_revenue = Transaction.objects.filter(
            status='success',
            transaction_type='wallet_topup',
            created_at__date__gte=month_start,
        ).aggregate(total=Sum('amount'))['total'] or 0

        trips_today = Trip.objects.filter(date=today).count()
        trips_completed = Trip.objects.filter(date=today, status='completed').count()

        bookings_today = Booking.objects.filter(
            created_at__date=today, status='confirmed'
        ).count()

        return Response({
            'students': {
                'total': total_students,
                'active': active_students,
                'inactive': total_students - active_students,
            },
            'revenue': {
                'all_time': float(total_revenue),
                'this_month': float(monthly_revenue),
            },
            'trips': {
                'today_total': trips_today,
                'today_completed': trips_completed,
            },
            'bookings_today': bookings_today,
        })


class RevenueChartView(APIView):
    """Daily revenue for the last 30 days — for chart rendering."""
    permission_classes = [IsAdminOrStaff]

    def get(self, request):
        days = int(request.query_params.get('days', 30))
        since = timezone.now().date() - timedelta(days=days)

        data = (
            Transaction.objects
            .filter(status='success', created_at__date__gte=since)
            .annotate(day=TruncDate('created_at'))
            .values('day')
            .annotate(total=Sum('amount'), count=Count('id'))
            .order_by('day')
        )
        return Response(list(data))


class MonthlyStatsView(APIView):
    """Monthly bookings and revenue for the last 12 months."""
    permission_classes = [IsAdminOrStaff]

    def get(self, request):
        since = timezone.now() - timedelta(days=365)

        revenue = (
            Transaction.objects
            .filter(status='success', created_at__gte=since)
            .annotate(month=TruncMonth('created_at'))
            .values('month')
            .annotate(total=Sum('amount'))
            .order_by('month')
        )
        bookings = (
            Booking.objects
            .filter(created_at__gte=since)
            .annotate(month=TruncMonth('created_at'))
            .values('month')
            .annotate(count=Count('id'))
            .order_by('month')
        )
        return Response({'revenue': list(revenue), 'bookings': list(bookings)})


class RoutePopularityView(APIView):
    """Bookings per route — for bar chart."""
    permission_classes = [IsAdminOrStaff]

    def get(self, request):
        data = (
            Booking.objects
            .values('trip__schedule__route__name', 'trip__schedule__route__id')
            .annotate(booking_count=Count('id'), revenue=Sum('amount_paid'))
            .order_by('-booking_count')
        )
        return Response(list(data))


class StudentUsageReportView(APIView):
    """Per-student usage summary. Supports CSV export."""
    permission_classes = [IsAdminOrStaff]

    def get(self, request):
        export = request.query_params.get('export', 'json')

        students = (
            StudentProfile.objects
            .select_related('user')
            .annotate(
                total_bookings=Count('user__bookings'),
                total_spent=Sum('user__bookings__amount_paid'),
            )
            .order_by('-total_bookings')
        )

        if export == 'csv':
            response = HttpResponse(content_type='text/csv')
            response['Content-Disposition'] = 'attachment; filename="student_usage.csv"'
            writer = csv.writer(response)
            writer.writerow([
                'Admission No', 'Name', 'Email', 'Faculty',
                'Transport Status', 'Wallet Balance', 'Total Trips', 'Total Spent (KES)'
            ])
            for s in students:
                writer.writerow([
                    s.admission_number,
                    s.user.get_full_name(),
                    s.user.email,
                    s.faculty,
                    s.transport_status,
                    float(s.wallet_balance),
                    s.total_bookings or 0,
                    float(s.total_spent or 0),
                ])
            return response

        # JSON
        result = []
        for s in students:
            result.append({
                'admission_number': s.admission_number,
                'name': s.user.get_full_name(),
                'email': s.user.email,
                'faculty': s.faculty,
                'transport_status': s.transport_status,
                'wallet_balance': float(s.wallet_balance),
                'total_bookings': s.total_bookings or 0,
                'total_spent': float(s.total_spent or 0),
            })
        return Response(result)


class PaymentReportView(APIView):
    """Transaction report with date range filtering. Supports CSV."""
    permission_classes = [IsAdminOrStaff]

    def get(self, request):
        export = request.query_params.get('export', 'json')
        date_from = request.query_params.get('from')
        date_to = request.query_params.get('to')

        qs = Transaction.objects.select_related('user').filter(status='success')
        if date_from:
            qs = qs.filter(created_at__date__gte=date_from)
        if date_to:
            qs = qs.filter(created_at__date__lte=date_to)

        if export == 'csv':
            response = HttpResponse(content_type='text/csv')
            response['Content-Disposition'] = 'attachment; filename="payment_report.csv"'
            writer = csv.writer(response)
            writer.writerow([
                'Reference', 'Student', 'Email', 'Method',
                'Type', 'Amount (KES)', 'Date'
            ])
            for t in qs:
                writer.writerow([
                    t.reference, t.user.get_full_name(), t.user.email,
                    t.payment_method, t.transaction_type,
                    float(t.amount), t.created_at.strftime('%Y-%m-%d %H:%M'),
                ])
            return response

        from apps.payments.views import TxnSerializer
        return Response(TxnSerializer(qs, many=True).data)
