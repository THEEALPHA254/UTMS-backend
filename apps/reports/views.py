"""
Reports app — analytics and summaries for admin/staff.
All endpoints require staff or admin role.
"""
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import permissions
from django.db.models import Sum, Count, Q
from django.utils import timezone
from datetime import timedelta

from apps.transport.models import Trip, Booking, Route
from apps.payments.models import Transaction
from apps.accounts.models import User, StudentProfile


class IsAdminOrStaff(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.role in ['admin', 'staff']


class DashboardSummaryView(APIView):
    """High-level stats for the admin dashboard."""
    permission_classes = [IsAdminOrStaff]

    def get(self, request):
        today = timezone.now().date()
        month_start = today.replace(day=1)

        total_students = StudentProfile.objects.count()
        active_students = StudentProfile.objects.filter(
            transport_status='active'
        ).count()
        total_drivers = User.objects.filter(role='driver').count()

        trips_today = Trip.objects.filter(date=today).count()
        trips_this_month = Trip.objects.filter(date__gte=month_start).count()
        active_trips = Trip.objects.filter(status='in_progress').count()

        revenue_today = Transaction.objects.filter(
            status='success',
            transaction_type='trip_payment',
            created_at__date=today,
        ).aggregate(total=Sum('amount'))['total'] or 0

        revenue_month = Transaction.objects.filter(
            status='success',
            transaction_type='trip_payment',
            created_at__date__gte=month_start,
        ).aggregate(total=Sum('amount'))['total'] or 0

        bookings_today = Booking.objects.filter(
            created_at__date=today,
            status__in=['confirmed', 'completed'],
        ).count()

        return Response({
            'students': {
                'total': total_students,
                'active': active_students,
                'inactive': total_students - active_students,
            },
            'drivers': {
                'total': total_drivers,
            },
            'trips': {
                'today': trips_today,
                'this_month': trips_this_month,
                'active_now': active_trips,
            },
            'bookings': {
                'today': bookings_today,
            },
            'revenue': {
                'today': float(revenue_today),
                'this_month': float(revenue_month),
                'currency': 'KES',
            },
        })


class RevenueReportView(APIView):
    """Monthly revenue breakdown."""
    permission_classes = [IsAdminOrStaff]

    def get(self, request):
        # Last 6 months
        months = []
        today = timezone.now().date()
        for i in range(5, -1, -1):
            d = today.replace(day=1) - timedelta(days=i * 28)
            month_start = d.replace(day=1)
            if d.month == 12:
                month_end = d.replace(year=d.year + 1, month=1, day=1)
            else:
                month_end = d.replace(month=d.month + 1, day=1)

            revenue = Transaction.objects.filter(
                status='success',
                transaction_type='trip_payment',
                created_at__date__gte=month_start,
                created_at__date__lt=month_end,
            ).aggregate(total=Sum('amount'))['total'] or 0

            topups = Transaction.objects.filter(
                status='success',
                transaction_type='wallet_topup',
                created_at__date__gte=month_start,
                created_at__date__lt=month_end,
            ).aggregate(total=Sum('amount'))['total'] or 0

            months.append({
                'month': month_start.strftime('%b %Y'),
                'trip_revenue': float(revenue),
                'wallet_topups': float(topups),
                'total': float(revenue) + float(topups),
            })

        return Response({'months': months})


class TripReportView(APIView):
    """Trip statistics."""
    permission_classes = [IsAdminOrStaff]

    def get(self, request):
        today = timezone.now().date()
        month_start = today.replace(day=1)

        by_status = Trip.objects.values('status').annotate(count=Count('id'))
        by_route = Booking.objects.filter(
            status__in=['confirmed', 'completed'],
            created_at__date__gte=month_start,
        ).values(
            'trip__schedule__route__origin',
            'trip__schedule__route__destination',
        ).annotate(bookings=Count('id')).order_by('-bookings')[:10]

        return Response({
            'by_status': list(by_status),
            'popular_routes_this_month': list(by_route),
            'total_trips': Trip.objects.count(),
            'completed_trips': Trip.objects.filter(status='completed').count(),
        })


class StudentReportView(APIView):
    """Student transport usage stats."""
    permission_classes = [IsAdminOrStaff]

    def get(self, request):
        top_users = Booking.objects.filter(
            status__in=['confirmed', 'completed']
        ).values(
            'student__first_name', 'student__last_name',
            'student__student_profile__admission_number',
        ).annotate(trips=Count('id')).order_by('-trips')[:10]

        by_faculty = StudentProfile.objects.values('faculty').annotate(
            count=Count('id')
        ).order_by('-count')

        return Response({
            'top_users': list(top_users),
            'by_faculty': list(by_faculty),
            'total_bookings': Booking.objects.filter(
                status__in=['confirmed', 'completed']
            ).count(),
        })
