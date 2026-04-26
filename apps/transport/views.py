from rest_framework import generics, status, permissions, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.decorators import action
from django.utils import timezone
from django.db import transaction
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from .models import Route, Bus, Schedule, Trip, Booking, BusLocation
from .serializers import (
    RouteSerializer, BusSerializer, ScheduleSerializer,
    TripSerializer, BookingSerializer, CreateBookingSerializer,
    BusLocationSerializer, UpdateBusLocationSerializer
)
from apps.accounts.models import StudentProfile
import json


class IsAdminOrStaff(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.role in ['admin', 'staff']


# ─── Routes ────────────────────────────────────────────────────────────────────

class RouteViewSet(viewsets.ModelViewSet):
    queryset = Route.objects.filter(is_active=True)
    serializer_class = RouteSerializer
    search_fields = ['name', 'origin', 'destination']

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [permissions.IsAuthenticated()]
        return [IsAdminOrStaff()]


# ─── Buses ─────────────────────────────────────────────────────────────────────

class BusViewSet(viewsets.ModelViewSet):
    queryset = Bus.objects.select_related('assigned_route', 'driver')
    serializer_class = BusSerializer
    filterset_fields = ['status', 'assigned_route']

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [permissions.IsAuthenticated()]
        return [IsAdminOrStaff()]


# ─── Schedules ─────────────────────────────────────────────────────────────────

class ScheduleViewSet(viewsets.ModelViewSet):
    queryset = Schedule.objects.filter(is_active=True).select_related('route', 'bus')
    serializer_class = ScheduleSerializer
    filterset_fields = ['route', 'bus', 'day_of_week', 'is_active']

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [permissions.IsAuthenticated()]
        return [IsAdminOrStaff()]


# ─── Trips ─────────────────────────────────────────────────────────────────────

class TripViewSet(viewsets.ModelViewSet):
    queryset = Trip.objects.select_related('schedule__route', 'schedule__bus')
    serializer_class = TripSerializer
    filterset_fields = ['status', 'date', 'schedule__route']

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [permissions.IsAuthenticated()]
        return [IsAdminOrStaff()]

    @action(detail=True, methods=['get'])
    def location(self, request, pk=None):
        """Get live location of a trip's bus."""
        trip = self.get_object()
        return Response({
            'trip_id': trip.id,
            'latitude': trip.current_latitude,
            'longitude': trip.current_longitude,
            'last_update': trip.last_location_update,
            'status': trip.status,
        })

    @action(detail=True, methods=['patch'], permission_classes=[IsAdminOrStaff])
    def update_status(self, request, pk=None):
        trip = self.get_object()
        new_status = request.data.get('status')
        if new_status not in [c[0] for c in Trip.Status.choices]:
            return Response({'error': 'Invalid status.'}, status=400)
        trip.status = new_status
        if new_status == Trip.Status.IN_PROGRESS:
            trip.actual_departure = timezone.now()
        elif new_status == Trip.Status.COMPLETED:
            trip.actual_arrival = timezone.now()
        trip.save()
        return Response(TripSerializer(trip).data)


# ─── Bookings ──────────────────────────────────────────────────────────────────

class MyBookingsView(generics.ListAPIView):
    """Student: list own bookings."""
    serializer_class = BookingSerializer

    def get_queryset(self):
        return Booking.objects.filter(
            student=self.request.user
        ).select_related('trip__schedule__route', 'trip__schedule__bus').order_by('-created_at')


class CreateBookingView(APIView):
    """Student: book a seat on a trip (optionally for a peer)."""

    @transaction.atomic
    def post(self, request):
        serializer = CreateBookingSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        trip = Trip.objects.select_for_update().get(pk=serializer.validated_data['trip_id'])
        payer = request.user  # the person making the request & paying

        # Determine who the booking is FOR
        admission = serializer.validated_data.get('student_admission')
        if admission:
            try:
                profile = StudentProfile.objects.get(admission_number=admission)
                beneficiary = profile.user
            except StudentProfile.DoesNotExist:
                return Response({'error': 'Student not found.'}, status=404)
        else:
            beneficiary = payer

        # Check duplicate booking
        if Booking.objects.filter(student=beneficiary, trip=trip).exists():
            return Response({'error': 'This student already has a booking for this trip.'}, status=400)

        fare = trip.schedule.route.fare

        # Deduct from payer's wallet
        payer_profile = payer.student_profile
        if payer_profile.wallet_balance < fare:
            return Response({'error': f'Insufficient wallet balance. Required: KES {fare}'}, status=400)

        payer_profile.wallet_balance -= fare
        payer_profile.save()

        # Create booking
        booking = Booking.objects.create(
            student=beneficiary,
            trip=trip,
            booked_by=payer if payer != beneficiary else None,
            status=Booking.Status.CONFIRMED,
            amount_paid=fare,
        )

        # Update seat count
        trip.seats_booked += 1
        trip.save()

        return Response(BookingSerializer(booking).data, status=201)


class AllBookingsView(generics.ListAPIView):
    """Admin/Staff: view all bookings."""
    serializer_class = BookingSerializer
    permission_classes = [IsAdminOrStaff]
    queryset = Booking.objects.select_related(
        'student', 'trip__schedule__route', 'trip__schedule__bus', 'booked_by'
    ).order_by('-created_at')
    filterset_fields = ['status', 'trip', 'trip__schedule__route']
    search_fields = ['student__first_name', 'student__last_name', 'student__student_profile__admission_number']


class MarkBoardedView(APIView):
    """Driver/Staff: mark a student as boarded via QR code."""
    permission_classes = [IsAdminOrStaff]

    def post(self, request):
        qr_code = request.data.get('qr_code')
        try:
            booking = Booking.objects.get(qr_code=qr_code, status=Booking.Status.CONFIRMED)
        except Booking.DoesNotExist:
            return Response({'error': 'Invalid or already used QR code.'}, status=404)
        booking.boarded = True
        booking.boarded_at = timezone.now()
        booking.status = Booking.Status.COMPLETED
        booking.save()
        return Response({'message': 'Boarding confirmed.', 'student': booking.student.get_full_name()})


# ─── Real-Time Bus Location (Driver Push) ─────────────────────────────────────

class PushBusLocationView(APIView):
    """Driver: push GPS coordinates. Broadcasts to WebSocket consumers."""

    def post(self, request):
        if request.user.role != 'driver':
            return Response({'error': 'Only drivers can push location.'}, status=403)

        serializer = UpdateBusLocationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            trip = Trip.objects.get(pk=data['trip_id'], status=Trip.Status.IN_PROGRESS)
        except Trip.DoesNotExist:
            return Response({'error': 'Trip not found or not in progress.'}, status=404)

        # Persist to DB
        BusLocation.objects.create(
            trip=trip,
            latitude=data['latitude'],
            longitude=data['longitude'],
            speed_kmh=data['speed_kmh'],
        )
        trip.current_latitude = data['latitude']
        trip.current_longitude = data['longitude']
        trip.last_location_update = timezone.now()
        trip.save(update_fields=['current_latitude', 'current_longitude', 'last_location_update'])

        # Broadcast via WebSocket
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f"trip_{trip.id}",
            {
                "type": "location_update",
                "latitude": str(data['latitude']),
                "longitude": str(data['longitude']),
                "speed_kmh": str(data['speed_kmh']),
            }
        )
        return Response({'message': 'Location updated.'})
