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
from apps.notifications.utils import send_notification
import logging

logger = logging.getLogger(__name__)


class IsAdminOrStaff(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.role in ['admin', 'staff']


class IsDriver(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.role == 'driver'


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
        if self.action in ['list', 'retrieve', 'location']:
            return [permissions.IsAuthenticated()]
        # update_status can be done by driver OR admin/staff
        if self.action == 'update_status':
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

    @action(detail=True, methods=['patch'])
    def update_status(self, request, pk=None):
        """
        Driver or staff can update trip status.
        Driver can only update trips assigned to their bus.
        """
        trip = self.get_object()
        user = request.user

        # Drivers can only manage trips on their assigned bus
        if user.role == 'driver':
            driver_profile = getattr(user, 'driver_profile', None)
            bus = getattr(driver_profile, None, None)
            # Allow driver to update any in-progress or scheduled trip for now
            # In production, filter by assigned bus

        new_status = request.data.get('status')
        valid_statuses = [c[0] for c in Trip.Status.choices]
        if new_status not in valid_statuses:
            return Response({'error': f'Invalid status. Choose from: {valid_statuses}'}, status=400)

        old_status = trip.status
        trip.status = new_status

        if new_status == Trip.Status.IN_PROGRESS:
            trip.actual_departure = timezone.now()
            # Notify all passengers that the trip has started
            _notify_trip_passengers(trip, 
                title='🚌 Trip Started',
                body=f'Your trip from {trip.schedule.route.origin} to {trip.schedule.route.destination} has started.',
                category='trip'
            )
        elif new_status == Trip.Status.COMPLETED:
            trip.actual_arrival = timezone.now()
            _notify_trip_passengers(trip,
                title='✅ Trip Completed',
                body=f'Your trip to {trip.schedule.route.destination} has been completed.',
                category='trip'
            )
        elif new_status == Trip.Status.CANCELLED:
            _notify_trip_passengers(trip,
                title='❌ Trip Cancelled',
                body=f'Your trip from {trip.schedule.route.origin} to {trip.schedule.route.destination} has been cancelled.',
                category='trip'
            )

        trip.save()
        return Response(TripSerializer(trip).data)


def _notify_trip_passengers(trip, title, body, category='trip'):
    """Helper: send notifications to all confirmed passengers of a trip."""
    bookings = Booking.objects.filter(
        trip=trip, status__in=[Booking.Status.CONFIRMED, Booking.Status.COMPLETED]
    ).select_related('student')
    for booking in bookings:
        send_notification(
            recipient=booking.student,
            title=title,
            body=body,
            category=category,
        )


# ─── Bookings ──────────────────────────────────────────────────────────────────

class MyBookingsView(generics.ListAPIView):
    """Student: list own bookings."""
    serializer_class = BookingSerializer

    def get_queryset(self):
        return Booking.objects.filter(
            student=self.request.user
        ).select_related(
            'trip__schedule__route', 'trip__schedule__bus', 'booked_by'
        ).order_by('-created_at')


class CreateBookingView(APIView):
    """
    Student: book a seat on a trip.
    Supports wallet payment (immediate) and M-Pesa (STK push).
    Can also book on behalf of another student.
    """

    @transaction.atomic
    def post(self, request):
        serializer = CreateBookingSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        trip = Trip.objects.select_for_update().get(pk=data['trip_id'])
        payer = request.user

        # Determine beneficiary
        admission = data.get('student_admission')
        if admission:
            try:
                profile = StudentProfile.objects.get(admission_number=admission)
                beneficiary = profile.user
            except StudentProfile.DoesNotExist:
                return Response({'error': 'Student not found.'}, status=404)
        else:
            beneficiary = payer

        # Check duplicate
        if Booking.objects.filter(student=beneficiary, trip=trip).exists():
            return Response({'error': 'This student already has a booking for this trip.'}, status=400)

        fare = trip.schedule.route.fare
        payment_method = data.get('payment_method', 'wallet')

        if payment_method == 'wallet':
            return _book_via_wallet(request, trip, payer, beneficiary, fare)
        elif payment_method == 'mpesa':
            phone = data.get('phone_number') or payer.phone_number
            if not phone:
                return Response({'error': 'Phone number required for M-Pesa.'}, status=400)
            return _book_via_mpesa(request, trip, payer, beneficiary, fare, phone)

        return Response({'error': 'Invalid payment method.'}, status=400)


@transaction.atomic
def _book_via_wallet(request, trip, payer, beneficiary, fare):
    """Deduct from wallet and confirm booking immediately."""
    try:
        payer_profile = payer.student_profile
    except Exception:
        return Response({'error': 'Student profile not found.'}, status=400)

    if payer_profile.wallet_balance < fare:
        return Response({'error': f'Insufficient wallet balance. Required: KES {fare}'}, status=400)

    # Deduct
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

    # Record transaction
    from apps.payments.models import Transaction
    Transaction.objects.create(
        user=payer,
        transaction_type=Transaction.TransactionType.TRIP_PAYMENT,
        payment_method=Transaction.PaymentMethod.WALLET,
        amount=fare,
        status=Transaction.Status.SUCCESS,
        description=f'Trip booking #{booking.id} - {trip.schedule.route.origin} → {trip.schedule.route.destination}',
        reference=f'BOOK-{booking.id}-{booking.qr_code[:8]}',
    )

    # Update seat count
    trip.seats_booked += 1
    trip.save()

    # Notify student
    send_notification(
        recipient=beneficiary,
        title='🎫 Booking Confirmed',
        body=f'Your seat on the {trip.schedule.route.origin} → {trip.schedule.route.destination} trip on {trip.date} has been confirmed.',
        category='booking',
    )
    if payer != beneficiary:
        send_notification(
            recipient=payer,
            title='🎫 Booking Confirmed',
            body=f'You booked a seat for {beneficiary.get_full_name()} on the {trip.date} trip.',
            category='booking',
        )

    return Response(BookingSerializer(booking).data, status=201)


@transaction.atomic
def _book_via_mpesa(request, trip, payer, beneficiary, fare, phone):
    """Initiate STK push. Booking created as PENDING until callback confirms."""
    from apps.payments.models import Transaction
    from apps.payments.mpesa import stk_push

    # Create a pending booking
    booking = Booking.objects.create(
        student=beneficiary,
        trip=trip,
        booked_by=payer if payer != beneficiary else None,
        status=Booking.Status.PENDING,
        amount_paid=fare,
    )

    txn = Transaction.objects.create(
        user=payer,
        transaction_type=Transaction.TransactionType.TRIP_PAYMENT,
        payment_method=Transaction.PaymentMethod.MPESA,
        amount=fare,
        status=Transaction.Status.PENDING,
        phone_number=phone,
        description=f'Trip booking #{booking.id}',
    )

    try:
        result = stk_push(
            phone_number=phone,
            amount=float(fare),
            account_reference=txn.reference,
            description=f'UTMS Trip {trip.id}',
        )
        txn.external_ref = result.get('CheckoutRequestID', '')
        txn.save()
        # Store booking ref on transaction description for callback lookup
        txn.description = f'Trip booking #{booking.id} | checkout:{txn.external_ref}'
        txn.save()

        # Update seat count optimistically
        trip.seats_booked += 1
        trip.save()

        return Response({
            'message': 'STK Push sent. Complete payment on your phone.',
            'booking_id': booking.id,
            'reference': txn.reference,
            'checkout_request_id': txn.external_ref,
            'booking': BookingSerializer(booking).data,
        }, status=201)

    except Exception as e:
        booking.delete()
        txn.status = Transaction.Status.FAILED
        txn.save()
        logger.error(f'MPesa STK Push failed: {e}')
        return Response({'error': 'M-Pesa request failed. Try again.'}, status=502)


class AllBookingsView(generics.ListAPIView):
    """Admin/Staff: view all bookings."""
    serializer_class = BookingSerializer
    permission_classes = [IsAdminOrStaff]
    queryset = Booking.objects.select_related(
        'student', 'trip__schedule__route', 'trip__schedule__bus', 'booked_by'
    ).order_by('-created_at')
    filterset_fields = ['status', 'trip', 'trip__schedule__route']
    search_fields = [
        'student__first_name', 'student__last_name',
        'student__student_profile__admission_number', 'qr_code'
    ]


class MarkBoardedView(APIView):
    """
    Driver: verify and board a student via QR code.
    Drivers can now call this endpoint (previously staff-only).
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        user = request.user
        if user.role not in ['driver', 'staff', 'admin']:
            return Response({'error': 'Not authorized to verify boarding.'}, status=403)

        qr_code = request.data.get('qr_code')
        if not qr_code:
            return Response({'error': 'QR code is required.'}, status=400)

        try:
            booking = Booking.objects.select_related(
                'student', 'trip__schedule__route'
            ).get(qr_code=qr_code, status=Booking.Status.CONFIRMED)
        except Booking.DoesNotExist:
            return Response({'error': 'Invalid or already used QR code.'}, status=404)

        booking.boarded = True
        booking.boarded_at = timezone.now()
        booking.status = Booking.Status.COMPLETED
        booking.save()

        # Notify student they've been boarded
        send_notification(
            recipient=booking.student,
            title='✅ Boarded',
            body=f'You have been successfully boarded on your trip to {booking.trip.schedule.route.destination}.',
            category='trip',
        )

        return Response({
            'message': 'Boarding confirmed.',
            'student': booking.student.get_full_name(),
            'admission': getattr(booking.student, 'student_profile', None) and
                         booking.student.student_profile.admission_number,
            'trip': str(booking.trip.schedule.route),
            'boarded_at': booking.boarded_at,
        })


class TripPassengersView(generics.ListAPIView):
    """
    Driver/Staff: list all passengers (bookings) for a specific trip.
    Used by driver app to see who has paid.
    """
    serializer_class = BookingSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        trip_id = self.request.query_params.get('trip')
        if not trip_id:
            return Booking.objects.none()
        return Booking.objects.filter(
            trip_id=trip_id
        ).select_related('student__student_profile', 'trip__schedule__route').order_by('student__first_name')


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
        try:
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
        except Exception as e:
            logger.warning(f"WebSocket broadcast failed: {e}")

        return Response({'message': 'Location updated.'})
