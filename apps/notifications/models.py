from django.db import models
from django.conf import settings


class Notification(models.Model):
    class Category(models.TextChoices):
        BOOKING = 'booking', 'Booking'
        PAYMENT = 'payment', 'Payment'
        TRIP = 'trip', 'Trip Update'
        SYSTEM = 'system', 'System'

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notifications'
    )
    title = models.CharField(max_length=200)
    body = models.TextField()
    category = models.CharField(max_length=20, choices=Category.choices, default=Category.SYSTEM)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'notifications'
        ordering = ['-created_at']

    def __str__(self):
        return f"Notif → {self.recipient}: {self.title}"
