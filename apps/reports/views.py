"""
Reports app — analytics, summaries, and exportable reports for admin/staff.
All endpoints require staff or admin role.
"""
import csv
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import permissions
from rest_framework.pagination import PageNumberPagination
from django.db.models import Sum, Count, Avg, Q
from django.http import HttpResponse
from django.utils import timezone
from datetime import timedelta

from apps.transport.models import Trip, Booking, Route, Bus, Schedule
from apps.payments.models import Transaction
from apps.accounts.models import User, StudentProfile, DriverProfile


class IsAdminOrStaff(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.role in ['admin', 'staff']


class ReportPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 500

    def get_paginated_response(self, data):
        return Response({
            'count': self.page.paginator.count,
            'next': self.get_next_link(),
            'previous': self.get_previous_link(),
            'results': data,
        })


def _parse_date(value):
    from datetime import date
    if not value:
        return None
    try:
        from datetime import datetime
        return datetime.strptime(value, '%Y-%m-%d').date()
    except ValueError:
        return None


class DashboardSummaryView(APIView):
    """High-level stats for the admin dashboard."""
    permission_classes = [IsAdminOrStaff]

    def get(self, request):
        today = timezone.now().date()
        month_start = today.replace(day=1)

        total_students = StudentProfile.objects.count()
        active_students = StudentProfile.objects.filter(transport_status='active').count()
        total_drivers = User.objects.filter(role='driver').count()

        trips_today = Trip.objects.filter(date=today).count()
        trips_today_completed = Trip.objects.filter(date=today, status='completed').count()
        trips_this_month = Trip.objects.filter(date__gte=month_start).count()
        active_trips = Trip.objects.filter(status='in_progress').count()

        revenue_today = Transaction.objects.filter(
            status='success', transaction_type='trip_payment', created_at__date=today,
        ).aggregate(total=Sum('amount'))['total'] or 0

        revenue_month = Transaction.objects.filter(
            status='success', transaction_type='trip_payment', created_at__date__gte=month_start,
        ).aggregate(total=Sum('amount'))['total'] or 0

        bookings_today = Booking.objects.filter(
            created_at__date=today, status__in=['confirmed', 'completed'],
        ).count()

        return Response({
            'students': {'total': total_students, 'active': active_students, 'inactive': total_students - active_students},
            'drivers': {'total': total_drivers},
            'trips': {
                'today': trips_today, 'today_total': trips_today,
                'today_completed': trips_today_completed,
                'this_month': trips_this_month, 'active_now': active_trips,
            },
            'bookings': {'today': bookings_today},
            'bookings_today': bookings_today,
            'revenue': {'today': float(revenue_today), 'this_month': float(revenue_month), 'currency': 'KES'},
        })


class RevenueReportView(APIView):
    """Monthly revenue breakdown."""
    permission_classes = [IsAdminOrStaff]

    def get(self, request):
        months = []
        today = timezone.now().date()
        for i in range(5, -1, -1):
            year = today.year
            month = today.month - i
            while month <= 0:
                month += 12
                year -= 1
            month_start = today.replace(year=year, month=month, day=1)
            if month == 12:
                month_end = month_start.replace(year=year + 1, month=1, day=1)
            else:
                month_end = month_start.replace(month=month + 1, day=1)

            revenue = Transaction.objects.filter(
                status='success', transaction_type='trip_payment',
                created_at__date__gte=month_start, created_at__date__lt=month_end,
            ).aggregate(total=Sum('amount'))['total'] or 0

            topups = Transaction.objects.filter(
                status='success', transaction_type='wallet_topup',
                created_at__date__gte=month_start, created_at__date__lt=month_end,
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
            status__in=['confirmed', 'completed'], created_at__date__gte=month_start,
        ).values(
            'trip__schedule__route__origin', 'trip__schedule__route__destination',
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
            'total_bookings': Booking.objects.filter(status__in=['confirmed', 'completed']).count(),
        })


class MonthlyTripsReportView(APIView):
    """Monthly trips aggregated report with optional CSV export."""
    permission_classes = [IsAdminOrStaff]

    def get(self, request):
        date_from = _parse_date(request.query_params.get('date_from'))
        date_to = _parse_date(request.query_params.get('date_to'))
        route_id = request.query_params.get('route')

        today = timezone.now().date()
        if not date_from:
            date_from = today.replace(day=1).replace(month=1) if today.month > 6 else (today - timedelta(days=180)).replace(day=1)
        if not date_to:
            date_to = today

        qs = Trip.objects.filter(date__gte=date_from, date__lte=date_to)
        if route_id:
            qs = qs.filter(schedule__route_id=route_id)

        from django.db.models.functions import TruncMonth
        monthly = qs.annotate(month=TruncMonth('date')).values('month').annotate(
            total_trips=Count('id'),
            total_passengers=Sum('seats_booked'),
        ).order_by('month')

        rows = []
        for m in monthly:
            month_str = m['month'].strftime('%b %Y') if m['month'] else ''
            total_trips = m['total_trips'] or 0
            total_passengers = m['total_passengers'] or 0

            revenue = Transaction.objects.filter(
                status='success',
                transaction_type='trip_payment',
                created_at__date__gte=m['month'],
                created_at__date__lt=(m['month'].replace(month=m['month'].month % 12 + 1, day=1)
                                      if m['month'].month < 12
                                      else m['month'].replace(year=m['month'].year + 1, month=1, day=1)),
            ).aggregate(total=Sum('amount'))['total'] or 0

            rows.append({
                'month': month_str,
                'total_trips': total_trips,
                'total_passengers': total_passengers,
                'total_revenue': float(revenue),
                'avg_passengers_per_trip': round(total_passengers / total_trips, 1) if total_trips else 0,
            })

        if request.query_params.get('export') == 'csv':
            response = HttpResponse(content_type='text/csv')
            response['Content-Disposition'] = 'attachment; filename="monthly_trips.csv"'
            writer = csv.writer(response)
            writer.writerow(['Month', 'Total Trips', 'Total Passengers', 'Total Revenue (KES)', 'Avg Passengers/Trip'])
            for r in rows:
                writer.writerow([r['month'], r['total_trips'], r['total_passengers'], r['total_revenue'], r['avg_passengers_per_trip']])
            return response

        return Response({'results': rows, 'date_from': str(date_from), 'date_to': str(date_to)})


class BookingReportView(APIView):
    """Detailed booking report with boarded/not-boarded filter and CSV export."""
    permission_classes = [IsAdminOrStaff]

    def get(self, request):
        qs = Booking.objects.select_related(
            'student__student_profile', 'trip__schedule__route', 'trip__schedule__bus'
        ).order_by('-created_at')

        date_from = _parse_date(request.query_params.get('date_from'))
        date_to = _parse_date(request.query_params.get('date_to'))
        if date_from:
            qs = qs.filter(created_at__date__gte=date_from)
        if date_to:
            qs = qs.filter(created_at__date__lte=date_to)

        boarded = request.query_params.get('boarded')
        if boarded == 'true':
            qs = qs.filter(boarded=True)
        elif boarded == 'false':
            qs = qs.filter(boarded=False)

        booking_status = request.query_params.get('status')
        if booking_status:
            qs = qs.filter(status=booking_status)

        route_id = request.query_params.get('route')
        if route_id:
            qs = qs.filter(trip__schedule__route_id=route_id)

        total = qs.count()
        boarded_count = qs.filter(boarded=True).count()
        no_show_count = qs.filter(boarded=False, status__in=['confirmed', 'completed']).count()

        if request.query_params.get('export') == 'csv':
            response = HttpResponse(content_type='text/csv')
            response['Content-Disposition'] = 'attachment; filename="bookings.csv"'
            writer = csv.writer(response)
            writer.writerow(['Admission No', 'Student Name', 'Route', 'Date', 'Time', 'Amount', 'Status', 'Boarded'])
            for b in qs:
                try:
                    admission = b.student.student_profile.admission_number
                except Exception:
                    admission = ''
                writer.writerow([
                    admission,
                    b.student.get_full_name(),
                    str(b.trip.schedule.route),
                    b.trip.date,
                    b.trip.schedule.departure_time,
                    b.amount_paid,
                    b.status,
                    'Yes' if b.boarded else 'No',
                ])
            return response

        paginator = ReportPagination()
        page = paginator.paginate_queryset(qs, request)
        rows = []
        for b in page:
            try:
                admission = b.student.student_profile.admission_number
            except Exception:
                admission = ''
            rows.append({
                'id': b.id,
                'admission_number': admission,
                'student_name': b.student.get_full_name(),
                'route': str(b.trip.schedule.route),
                'date': b.trip.date,
                'departure_time': b.trip.schedule.departure_time,
                'amount_paid': float(b.amount_paid),
                'status': b.status,
                'boarded': b.boarded,
                'created_at': b.created_at,
            })

        resp = paginator.get_paginated_response(rows)
        resp.data['summary'] = {
            'total_bookings': total,
            'boarded_count': boarded_count,
            'no_show_count': no_show_count,
            'no_show_rate': round(no_show_count / total * 100, 1) if total else 0,
        }
        return resp


class VehicleOccupancyReportView(APIView):
    """Per-trip vehicle occupancy report."""
    permission_classes = [IsAdminOrStaff]

    def get(self, request):
        qs = Trip.objects.select_related(
            'schedule__route', 'schedule__bus', 'schedule__bus__driver'
        ).order_by('-date')

        date_from = _parse_date(request.query_params.get('date_from'))
        date_to = _parse_date(request.query_params.get('date_to'))
        if date_from:
            qs = qs.filter(date__gte=date_from)
        if date_to:
            qs = qs.filter(date__lte=date_to)

        route_id = request.query_params.get('route')
        if route_id:
            qs = qs.filter(schedule__route_id=route_id)

        bus_id = request.query_params.get('bus')
        if bus_id:
            qs = qs.filter(schedule__bus_id=bus_id)

        if request.query_params.get('export') == 'csv':
            response = HttpResponse(content_type='text/csv')
            response['Content-Disposition'] = 'attachment; filename="vehicle_occupancy.csv"'
            writer = csv.writer(response)
            writer.writerow(['Date', 'Route', 'Vehicle (Plate)', 'Driver', 'Booked', 'Boarded', 'Capacity', 'Occupancy %'])
            for t in qs:
                boarded = Booking.objects.filter(trip=t, boarded=True).count()
                capacity = t.schedule.bus.capacity if t.schedule.bus else 0
                driver_name = t.schedule.bus.driver.get_full_name() if (t.schedule.bus and t.schedule.bus.driver) else 'Unassigned'
                writer.writerow([
                    t.date, str(t.schedule.route),
                    t.schedule.bus.plate_number if t.schedule.bus else '',
                    driver_name, t.seats_booked, boarded, capacity,
                    round(boarded / capacity * 100, 1) if capacity else 0,
                ])
            return response

        paginator = ReportPagination()
        page = paginator.paginate_queryset(qs, request)
        rows = []
        for t in page:
            boarded = Booking.objects.filter(trip=t, boarded=True).count()
            capacity = t.schedule.bus.capacity if t.schedule.bus else 0
            driver_name = t.schedule.bus.driver.get_full_name() if (t.schedule.bus and t.schedule.bus.driver) else 'Unassigned'
            rows.append({
                'trip_id': t.id,
                'date': t.date,
                'route': str(t.schedule.route),
                'plate_number': t.schedule.bus.plate_number if t.schedule.bus else '',
                'driver': driver_name,
                'seats_booked': t.seats_booked,
                'boarded': boarded,
                'capacity': capacity,
                'occupancy_pct': round(boarded / capacity * 100, 1) if capacity else 0,
            })
        return paginator.get_paginated_response(rows)


class RevenueDetailReportView(APIView):
    """Revenue breakdown by day/route with CSV export."""
    permission_classes = [IsAdminOrStaff]

    def get(self, request):
        date_from = _parse_date(request.query_params.get('date_from'))
        date_to = _parse_date(request.query_params.get('date_to'))
        today = timezone.now().date()
        if not date_from:
            date_from = today.replace(day=1)
        if not date_to:
            date_to = today

        from django.db.models.functions import TruncDate
        qs = Transaction.objects.filter(
            status='success', transaction_type='trip_payment',
            created_at__date__gte=date_from, created_at__date__lte=date_to,
        ).annotate(day=TruncDate('created_at')).values('day').annotate(
            total=Sum('amount'), count=Count('id')
        ).order_by('day')

        rows = [{'date': str(r['day']), 'transactions': r['count'], 'revenue': float(r['total'])} for r in qs]

        if request.query_params.get('export') == 'csv':
            response = HttpResponse(content_type='text/csv')
            response['Content-Disposition'] = 'attachment; filename="revenue.csv"'
            writer = csv.writer(response)
            writer.writerow(['Date', 'Transactions', 'Revenue (KES)'])
            for r in rows:
                writer.writerow([r['date'], r['transactions'], r['revenue']])
            return response

        total_revenue = sum(r['revenue'] for r in rows)
        return Response({'results': rows, 'total_revenue': total_revenue, 'date_from': str(date_from), 'date_to': str(date_to)})


class DriverPerformanceReportView(APIView):
    """Driver performance — trips, passengers, averages."""
    permission_classes = [IsAdminOrStaff]

    def get(self, request):
        date_from = _parse_date(request.query_params.get('date_from'))
        date_to = _parse_date(request.query_params.get('date_to'))

        qs = DriverProfile.objects.select_related('user').order_by('user__first_name')

        rows = []
        for dp in qs:
            trips_qs = Trip.objects.filter(schedule__bus__driver=dp.user)
            if date_from:
                trips_qs = trips_qs.filter(date__gte=date_from)
            if date_to:
                trips_qs = trips_qs.filter(date__lte=date_to)

            total_trips = trips_qs.count()
            completed_trips = trips_qs.filter(status='completed').count()
            total_passengers = trips_qs.aggregate(total=Sum('seats_booked'))['total'] or 0
            avg_passengers = round(total_passengers / total_trips, 1) if total_trips else 0

            bus = dp.user.assigned_buses.first()
            rows.append({
                'driver_id': dp.id,
                'name': dp.user.get_full_name(),
                'email': dp.user.email,
                'license_number': dp.license_number,
                'assigned_vehicle': bus.plate_number if bus else 'Unassigned',
                'total_trips': total_trips,
                'completed_trips': completed_trips,
                'total_passengers': total_passengers,
                'avg_passengers_per_trip': avg_passengers,
            })

        if request.query_params.get('export') == 'csv':
            response = HttpResponse(content_type='text/csv')
            response['Content-Disposition'] = 'attachment; filename="driver_performance.csv"'
            writer = csv.writer(response)
            writer.writerow(['Name', 'License', 'Vehicle', 'Total Trips', 'Completed', 'Total Passengers', 'Avg Passengers'])
            for r in rows:
                writer.writerow([r['name'], r['license_number'], r['assigned_vehicle'],
                                  r['total_trips'], r['completed_trips'], r['total_passengers'], r['avg_passengers_per_trip']])
            return response

        return Response({'results': rows})
