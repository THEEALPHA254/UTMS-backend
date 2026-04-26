from rest_framework import serializers
from .models import Route, Bus, Schedule, Trip, Booking, BusLocation
from apps.accounts.serializers import UserSerializer


class RouteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Route
        fields = '__all__'


class BusSerializer(serializers.ModelSerializer):
    driver_name = serializers.SerializerMethodField()
    route_name = serializers.SerializerMethodField()

    class Meta:
        model = Bus
        fields = '__all__'

    def get_driver_name(self, obj):
        return obj.driver.get_full_name() if obj.driver else None

    def get_route_name(self, obj):
        return str(obj.assigned_route) if obj.assigned_route else None


class ScheduleSerializer(serializers.ModelSerializer):
    route_detail = RouteSerializer(source='route', read_only=True)
    bus_detail = BusSerializer(source='bus', read_only=True)
    day_label = serializers.CharField(source='get_day_of_week_display', read_only=True)

    class Meta:
        model = Schedule
        fields = '__all__'


class TripSerializer(serializers.ModelSerializer):
    schedule_detail = ScheduleSerializer(source='schedule', read_only=True)
    available_seats = serializers.IntegerField(read_only=True)

    class Meta:
        model = Trip
        fields = '__all__'


class BookingSerializer(serializers.ModelSerializer):
    student_name = serializers.SerializerMethodField()
    trip_detail = TripSerializer(source='trip', read_only=True)
    booked_by_name = serializers.SerializerMethodField()

    class Meta:
        model = Booking
        fields = '__all__'
        read_only_fields = ['qr_code', 'boarded', 'boarded_at', 'created_at']

    def get_student_name(self, obj):
        return obj.student.get_full_name()

    def get_booked_by_name(self, obj):
        return obj.booked_by.get_full_name() if obj.booked_by else None


class CreateBookingSerializer(serializers.Serializer):
    trip_id = serializers.IntegerField()
    student_admission = serializers.CharField(required=False)  # for paying on behalf

    def validate_trip_id(self, value):
        try:
            trip = Trip.objects.get(pk=value, status=Trip.Status.SCHEDULED)
        except Trip.DoesNotExist:
            raise serializers.ValidationError("Trip not found or not available for booking.")
        if trip.available_seats <= 0:
            raise serializers.ValidationError("No available seats on this trip.")
        return value


class BusLocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = BusLocation
        fields = ['latitude', 'longitude', 'speed_kmh', 'recorded_at']


class UpdateBusLocationSerializer(serializers.Serializer):
    """Used by driver app to push GPS location."""
    trip_id = serializers.IntegerField()
    latitude = serializers.DecimalField(max_digits=10, decimal_places=7)
    longitude = serializers.DecimalField(max_digits=10, decimal_places=7)
    speed_kmh = serializers.DecimalField(max_digits=5, decimal_places=2, default=0)
