from django.db import models
from django.conf import settings


class Transaction(models.Model):
    class PaymentMethod(models.TextChoices):
        MPESA = 'mpesa', 'M-Pesa'
        CARD = 'card', 'Credit/Debit Card'
        WALLET = 'wallet', 'Wallet'

    class TransactionType(models.TextChoices):
        WALLET_TOPUP = 'wallet_topup', 'Wallet Top-Up'
        TRIP_PAYMENT = 'trip_payment', 'Trip Payment'
        REFUND = 'refund', 'Refund'

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        SUCCESS = 'success', 'Success'
        FAILED = 'failed', 'Failed'
        REFUNDED = 'refunded', 'Refunded'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='transactions'
    )
    transaction_type = models.CharField(max_length=30, choices=TransactionType.choices)
    payment_method = models.CharField(max_length=20, choices=PaymentMethod.choices)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    # External reference (M-Pesa CheckoutRequestID, Stripe PaymentIntent, etc.)
    external_ref = models.CharField(max_length=255, blank=True)
    # Internal reference
    reference = models.CharField(max_length=100, unique=True, blank=True)
    description = models.TextField(blank=True)
    phone_number = models.CharField(max_length=20, blank=True)  # for MPesa
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'transactions'
        ordering = ['-created_at']

    def __str__(self):
        return f"TXN {self.reference} - {self.user} - KES {self.amount}"

    def save(self, *args, **kwargs):
        if not self.reference:
            import uuid
            self.reference = f"UTMS-{uuid.uuid4().hex[:10].upper()}"
        super().save(*args, **kwargs)
