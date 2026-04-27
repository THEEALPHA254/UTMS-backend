# tasks.py
from celery import shared_task
from django.core.mail import send_mail
from django.conf import settings


@shared_task
def send_credentials_email(email: str, full_name: str, password: str, role: str):
    """
    Send login credentials to a newly created user.
    Called after staff creates a student, driver, or another staff member.
    """
    role_label = role.capitalize()
    subject = f"Your {role_label} Account Credentials"
    message = (
        f"Hello {full_name},\n\n"
        f"Your {role_label} account has been created.\n\n"
        f"Login Email: {email}\n"
        f"Temporary Password: {password}\n\n"
        f"Please log in and change your password immediately.\n\n"
        f"Regards,\nTransport Management System"
    )
    send_mail(
        subject,
        message,
        settings.DEFAULT_FROM_EMAIL,
        [email],
        fail_silently=False,
    )