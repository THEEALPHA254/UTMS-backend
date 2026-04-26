from django.db import models
from django.conf import settings
from django.utils import timezone


class Route(models.Model):
    name = models.CharField(max_length=200)
    origin = models.CharField(max_length=200)
    destination = models.CharField(max_length=200)
    distance_km = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    fare = models.DecimalField(max_digits=8, decimal_places=2)
    is_active = models.BooleanField(default=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'routes'

    def __str__(self):
        return f"{self.origin} → {self.destination}"


class Bus(models.Model):
    class Status(models.TextChoices):
        ACTIVE = 'active', 'Active'
        MAINTENANCE = 'maintenance', 'Under Maintenance'
        RETIRED = 'retired', 'Retired'

    bus_number = models.CharField(max_length=20, unique=True)
    plate_number = models.CharField(max_length=20, unique=True)
    capacity = models.PositiveIntegerField()
    model = models.CharField(max_length=100, blank=True)
    year = models.PositiveSmallIntegerField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    assigned_route = models.ForeignKey(
        Route, on_delete=models.SET_NULL, null=True, blank=True, related_name='buses'
    )
    driver = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='assigned_buses',
        limit_choices_to={'role': 'driver'}
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'buses'
        verbose_name_plural = 'Buses'

    def __str__(self):
        return f"Bus {self.bus_number} ({self.plate_number})"


class Schedule(models.Model):
    class DayOfWeek(models.IntegerChoices):
        MONDAY = 0, 'Monday'
        TUESDAY = 1, 'Tuesday'
        WEDNESDAY = 2, 'Wednesday'
        THURSDAY = 3, 'Thursday'
        FRIDAY = 4, 'Friday'
        SATURDAY = 5, 'Saturday'
        SUNDAY = 6, 'Sunday'

    route = models.ForeignKey(Route, on_delete=models.CASCADE, related_name='schedules')
    bus = models.ForeignKey(Bus, on_delete=models.CASCADE, related_name='schedules')
    day_of_week = models.IntegerField(choices=DayOfWeek.choices)
    departure_time = models.TimeField()
    arrival_time = models.TimeField()
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'schedules'
        unique_together = ['route', 'bus', 'day_of_week', 'departure_time']

    def __str__(self):
        return f"{self.route} - {self.get_day_of_week_display()} {self.departure_time}"


class Trip(models.Model):
    class Status(models.TextChoices):
        SCHEDULED = 'scheduled', 'Scheduled'
        IN_PROGRESS = 'in_progress', 'In Progress'
        COMPLETED = 'completed', 'Completed'
        CANCELLED = 'cancelled', 'Cancelled'

    schedule = models.ForeignKey(Schedule, on_delete=models.CASCADE, related_name='trips')
    date = models.DateField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.SCHEDULED)
    actual_departure = models.DateTimeField(null=True, blank=True)
    actual_arrival = models.DateTimeField(null=True, blank=True)
    seats_booked = models.PositiveIntegerField(default=0)
    # Real-time GPS
    current_latitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    current_longitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    last_location_update = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'trips'
        unique_together = ['schedule', 'date']

    def __str__(self):
        return f"Trip: {self.schedule} on {self.date}"

    @property
    def available_seats(self):
        return self.schedule.bus.capacity - self.seats_booked


class Booking(models.Model):
    class Status(models.TextChoices):
        CONFIRMED = 'confirmed', 'Confirmed'
        PENDING = 'pending', 'Pending Payment'
        CANCELLED = 'cancelled', 'Cancelled'
        COMPLETED = 'completed', 'Completed'

    student = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='bookings', limit_choices_to={'role': 'student'}
    )
    trip = models.ForeignKey(Trip, on_delete=models.CASCADE, related_name='bookings')
    booked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='bookings_made',
        help_text="Student who paid (can be different from student)"
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    seat_number = models.PositiveIntegerField(null=True, blank=True)
    amount_paid = models.DecimalField(max_digits=8, decimal_places=2)
    boarded = models.BooleanField(default=False)
    boarded_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    qr_code = models.CharField(max_length=255, unique=True, blank=True)

    class Meta:
        db_table = 'bookings'
        unique_together = ['student', 'trip']

    def __str__(self):
        return f"Booking #{self.id} - {self.student} on {self.trip}"

    def save(self, *args, **kwargs):
        if not self.qr_code:
            import uuid
            self.qr_code = str(uuid.uuid4())
        super().save(*args, **kwargs)


class BusLocation(models.Model):
    """Stores historical GPS trail for a trip."""
    trip = models.ForeignKey(Trip, on_delete=models.CASCADE, related_name='location_trail')
    latitude = models.DecimalField(max_digits=10, decimal_places=7)
    longitude = models.DecimalField(max_digits=10, decimal_places=7)
    speed_kmh = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'bus_locations'
        ordering = ['-recorded_at']
