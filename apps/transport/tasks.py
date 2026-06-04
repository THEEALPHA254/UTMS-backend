from celery import shared_task
from django.utils import timezone
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)


@shared_task
def auto_refund_no_shows():
    """
    Runs periodically. Finds bookings where:
    - Student paid from wallet (trip_payment via wallet)
    - Student did NOT board (boarded=False)
    - More than 24 hours have passed since the scheduled trip time
    Reverses the fare back to the student's wallet and marks booking as refunded.
    """
    from .models import Booking, Trip
    from apps.payments.models import Transaction
    from apps.accounts.models import StudentProfile
    from apps.notifications.utils import send_notification
    from django.db import transaction as db_transaction

    cutoff = timezone.now() - timedelta(hours=24)

    # Find eligible bookings: completed/confirmed, not boarded, trip ended >24h ago
    no_show_bookings = Booking.objects.select_related(
        'student__student_profile', 'trip__schedule'
    ).filter(
        boarded=False,
        status__in=['confirmed', 'completed'],
        trip__status='completed',
    ).exclude(status='refunded')

    refunded_count = 0
    for booking in no_show_bookings:
        try:
            trip = booking.trip
            schedule = trip.schedule
            # Build the datetime when the trip was scheduled to depart
            trip_dt = timezone.make_aware(
                timezone.datetime.combine(trip.date, schedule.departure_time)
            )
            if trip_dt > cutoff:
                continue  # Not yet 24h since the trip

            if booking.amount_paid <= 0:
                continue

            with db_transaction.atomic():
                # Credit wallet
                profile = booking.student.student_profile
                profile.wallet_balance += booking.amount_paid
                profile.save(update_fields=['wallet_balance'])

                # Log refund transaction
                Transaction.objects.create(
                    user=booking.student,
                    transaction_type=Transaction.TransactionType.REFUND,
                    payment_method=Transaction.PaymentMethod.WALLET,
                    amount=booking.amount_paid,
                    status=Transaction.Status.SUCCESS,
                    description=f'Auto-refund for no-show on booking #{booking.id} (trip {trip.id} on {trip.date})',
                )

                # Mark booking as refunded
                booking.status = 'refunded'
                booking.save(update_fields=['status'])

                send_notification(
                    recipient=booking.student,
                    title='💰 Fare Refunded',
                    body=f'KES {booking.amount_paid} has been refunded to your wallet as you did not board your trip on {trip.date}.',
                    category='payment',
                )

                refunded_count += 1
                logger.info(f'Auto-refunded KES {booking.amount_paid} for booking #{booking.id} (student: {booking.student.email})')

        except Exception as e:
            logger.error(f'Auto-refund failed for booking #{booking.id}: {e}')

    logger.info(f'Auto-refund task complete. Refunded {refunded_count} bookings.')
    return refunded_count
