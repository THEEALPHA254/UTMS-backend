from django.contrib import admin
from .models import Route, Bus, Schedule, Trip, Booking, BusLocation


@admin.register(Route)
class RouteAdmin(admin.ModelAdmin):
    list_display  = ('id', 'name', 'origin', 'destination', 'fare', 'distance_km', 'is_active', 'created_at')
    list_filter   = ('is_active',)
    search_fields = ('name', 'origin', 'destination')
    ordering      = ('name',)
    list_editable = ('is_active',)


@admin.register(Bus)
class BusAdmin(admin.ModelAdmin):
    list_display  = ('id', 'bus_number', 'plate_number', 'capacity', 'model', 'year', 'status', 'assigned_route', 'driver')
    list_filter   = ('status',)
    search_fields = ('bus_number', 'plate_number', 'model')
    ordering      = ('bus_number',)
    raw_id_fields = ('driver',)


@admin.register(Schedule)
class ScheduleAdmin(admin.ModelAdmin):
    list_display  = ('id', 'route', 'bus', 'get_day_of_week_display', 'departure_time', 'arrival_time', 'is_active')
    list_filter   = ('day_of_week', 'is_active', 'route')
    search_fields = ('route__name', 'route__origin', 'route__destination', 'bus__bus_number')
    ordering      = ('day_of_week', 'departure_time')
    list_editable = ('is_active',)


@admin.register(Trip)
class TripAdmin(admin.ModelAdmin):
    list_display  = ('id', 'schedule', 'date', 'status', 'seats_booked', 'available_seats',
                     'actual_departure', 'actual_arrival', 'last_location_update')
    list_filter   = ('status', 'date')
    search_fields = ('schedule__route__origin', 'schedule__route__destination', 'schedule__bus__bus_number')
    ordering      = ('-date',)
    readonly_fields = ('available_seats', 'last_location_update')
    date_hierarchy = 'date'

    @admin.display(description='Available Seats')
    def available_seats(self, obj):
        return obj.available_seats


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display  = ('id', 'student', 'trip', 'status', 'amount_paid', 'boarded', 'boarded_at', 'created_at')
    list_filter   = ('status', 'boarded')
    search_fields = ('student__email', 'student__first_name', 'student__last_name',
                     'qr_code', 'trip__schedule__route__origin')
    ordering      = ('-created_at',)
    readonly_fields = ('qr_code', 'created_at', 'boarded_at')
    raw_id_fields = ('student', 'booked_by', 'trip')
    date_hierarchy = 'created_at'


@admin.register(BusLocation)
class BusLocationAdmin(admin.ModelAdmin):
    list_display  = ('id', 'trip', 'latitude', 'longitude', 'speed_kmh', 'recorded_at')
    list_filter   = ('trip',)
    ordering      = ('-recorded_at',)
    readonly_fields = ('recorded_at',)
