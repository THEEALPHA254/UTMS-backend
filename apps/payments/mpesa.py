"""
Safaricom Daraja M-Pesa STK Push integration.
Docs: https://developer.safaricom.co.ke/Documentation
"""
import base64
import requests
from datetime import datetime
from django.conf import settings


def get_mpesa_token():
    """Obtain OAuth access token from Safaricom."""
    base_url = (
        'https://sandbox.safaricom.co.ke'
        if settings.MPESA_ENV == 'sandbox'
        else 'https://api.safaricom.co.ke'
    )
    credentials = f"{settings.MPESA_CONSUMER_KEY}:{settings.MPESA_CONSUMER_SECRET}"
    encoded = base64.b64encode(credentials.encode()).decode()
    response = requests.get(
        f"{base_url}/oauth/v1/generate?grant_type=client_credentials",
        headers={"Authorization": f"Basic {encoded}"},
        timeout=30,
    )
    response.raise_for_status()
    return response.json().get('access_token')


def generate_password():
    """Generate base64 encoded password for STK push."""
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    raw = f"{settings.MPESA_SHORTCODE}{settings.MPESA_PASSKEY}{timestamp}"
    password = base64.b64encode(raw.encode()).decode()
    return password, timestamp


def stk_push(phone_number: str, amount: float, account_reference: str, description: str):
    """
    Initiate STK Push to user's phone.
    Returns the API response dict or raises on failure.
    """
    base_url = (
        'https://sandbox.safaricom.co.ke'
        if settings.MPESA_ENV == 'sandbox'
        else 'https://api.safaricom.co.ke'
    )
    token = get_mpesa_token()
    password, timestamp = generate_password()

    # Normalize phone: 07XXXXXXXX → 2547XXXXXXXX
    phone = str(phone_number).strip().replace('+', '')
    if phone.startswith('0'):
        phone = '254' + phone[1:]

    payload = {
        "BusinessShortCode": settings.MPESA_SHORTCODE,
        "Password": password,
        "Timestamp": timestamp,
        "TransactionType": "CustomerPayBillOnline",
        "Amount": int(amount),
        "PartyA": phone,
        "PartyB": settings.MPESA_SHORTCODE,
        "PhoneNumber": phone,
        "CallBackURL": settings.MPESA_CALLBACK_URL,
        "AccountReference": account_reference,
        "TransactionDesc": description,
    }
    response = requests.post(
        f"{base_url}/mpesa/stkpush/v1/processrequest",
        json=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        timeout=30,
    )
    response.raise_for_status()
    return response.json()
