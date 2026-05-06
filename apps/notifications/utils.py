"""
Utility helpers for sending notifications throughout the app.
Import and call send_notification() from anywhere.
"""
import logging
from .models import Notification

logger = logging.getLogger(__name__)


def send_notification(recipient, title: str, body: str, category: str = 'system'):
    """
    Create a notification record for a user.
    In future, this can also trigger Firebase FCM push notification.
    """
    try:
        Notification.objects.create(
            recipient=recipient,
            title=title,
            body=body,
            category=category,
        )
    except Exception as e:
        logger.error(f"Failed to create notification for {recipient}: {e}")


def send_bulk_notification(recipients, title: str, body: str, category: str = 'system'):
    """Send the same notification to multiple users at once."""
    notifications = [
        Notification(recipient=r, title=title, body=body, category=category)
        for r in recipients
    ]
    try:
        Notification.objects.bulk_create(notifications, ignore_conflicts=True)
    except Exception as e:
        logger.error(f"Bulk notification failed: {e}")
