from rest_framework import generics, status, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from django.db import transaction
from django.utils import timezone
from .models import Transaction
from .mpesa import stk_push
from apps.accounts.models import StudentProfile
from apps.notifications.utils import send_notification
import logging

logger = logging.getLogger(__name__)


# ── Serializers (kept inline for simplicity) ──────────────────────────────────

from rest_framework import serializers as drf_serializers


class TxnSerializer(drf_serializers.ModelSerializer):
    transaction_type_display = drf_serializers.CharField(
        source='get_transaction_type_display', read_only=True
    )
    payment_method_display = drf_serializers.CharField(
        source='get_payment_method_display', read_only=True
    )
    status_display = drf_serializers.CharField(
        source='get_status_display', read_only=True
    )

    class Meta:
        model = Transaction
        fields = '__all__'


class TopUpWalletSerializer(drf_serializers.Serializer):
    amount = drf_serializers.DecimalField(max_digits=10, decimal_places=2, min_value=10)
    payment_method = drf_serializers.ChoiceField(choices=['mpesa', 'card'])
    phone_number = drf_serializers.CharField(required=False, allow_blank=True)

    def validate(self, data):
        if data['payment_method'] == 'mpesa' and not data.get('phone_number'):
            raise drf_serializers.ValidationError(
                {'phone_number': 'Phone number is required for M-Pesa.'}
            )
        return data


# ── Views ─────────────────────────────────────────────────────────────────────

class MyTransactionsView(generics.ListAPIView):
    """Student/Driver: view own transaction history."""
    serializer_class = TxnSerializer

    def get_queryset(self):
        return Transaction.objects.filter(
            user=self.request.user
        ).order_by('-created_at')


class AllTransactionsView(generics.ListAPIView):
    """Admin/Staff: view all transactions."""
    serializer_class = TxnSerializer
    permission_classes = [permissions.IsAdminUser]
    queryset = Transaction.objects.select_related('user').all()
    filterset_fields = ['status', 'transaction_type', 'payment_method']
    search_fields = ['user__email', 'reference', 'external_ref']


class WalletBalanceView(APIView):
    """Student: check wallet balance."""
    def get(self, request):
        try:
            profile = request.user.student_profile
            return Response({
                'balance': str(profile.wallet_balance),
                'currency': 'KES',
                'user': request.user.get_full_name(),
            })
        except Exception:
            return Response({'error': 'Student profile not found.'}, status=404)


class InitiateWalletTopUpView(APIView):
    """
    Student initiates a wallet top-up.
    - M-Pesa: triggers STK Push.
    - Card: placeholder for Stripe/Flutterwave.
    """
    @transaction.atomic
    def post(self, request):
        serializer = TopUpWalletSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        txn = Transaction.objects.create(
            user=request.user,
            transaction_type=Transaction.TransactionType.WALLET_TOPUP,
            payment_method=data['payment_method'],
            amount=data['amount'],
            status=Transaction.Status.PENDING,
            phone_number=data.get('phone_number', ''),
            description=f"Wallet top-up of KES {data['amount']}",
        )

        if data['payment_method'] == 'mpesa':
            phone = data.get('phone_number') or request.user.phone_number
            try:
                result = stk_push(
                    phone_number=phone,
                    amount=float(data['amount']),
                    account_reference=txn.reference,
                    description="UTMS Wallet Top-Up",
                )
                txn.external_ref = result.get('CheckoutRequestID', '')
                txn.save()
                return Response({
                    'message': 'STK Push sent. Complete payment on your phone.',
                    'reference': txn.reference,
                    'checkout_request_id': txn.external_ref,
                })
            except Exception as e:
                txn.status = Transaction.Status.FAILED
                txn.save()
                logger.error(f"MPesa STK Push failed: {e}")
                return Response({'error': 'M-Pesa request failed. Try again.'}, status=502)

        # Card
        return Response({
            'message': 'Transaction initiated.',
            'reference': txn.reference,
            'amount': str(data['amount']),
        })


class MpesaCallbackView(APIView):
    """
    Safaricom STK Push callback.
    Called directly by Safaricom after payment — no auth required.
    """
    permission_classes = [permissions.AllowAny]

    @transaction.atomic
    def post(self, request):
        try:
            body = request.data.get('Body', {})
            stk_callback = body.get('stkCallback', {})
            result_code = stk_callback.get('ResultCode')
            checkout_id = stk_callback.get('CheckoutRequestID')

            txn = Transaction.objects.select_for_update().get(external_ref=checkout_id)

            if result_code == 0:
                txn.status = Transaction.Status.SUCCESS
                txn.save()

                if txn.transaction_type == Transaction.TransactionType.WALLET_TOPUP:
                    # Credit wallet
                    profile = StudentProfile.objects.get(user=txn.user)
                    profile.wallet_balance += txn.amount
                    profile.save()
                    logger.info(f"Wallet topped up: {txn.user} +KES{txn.amount}")

                    send_notification(
                        recipient=txn.user,
                        title='💰 Wallet Topped Up',
                        body=f'KES {txn.amount} has been added to your wallet. New balance: KES {profile.wallet_balance}',
                        category='payment',
                    )

                elif txn.transaction_type == Transaction.TransactionType.TRIP_PAYMENT:
                    # Confirm pending booking
                    _confirm_mpesa_booking(txn)

            else:
                txn.status = Transaction.Status.FAILED
                txn.save()
                logger.warning(f"MPesa failed for {txn.reference}: code {result_code}")

                send_notification(
                    recipient=txn.user,
                    title='❌ Payment Failed',
                    body=f'Your M-Pesa payment of KES {txn.amount} failed. Please try again.',
                    category='payment',
                )

        except Transaction.DoesNotExist:
            logger.error(f"No transaction found for CheckoutRequestID: {checkout_id}")
        except Exception as e:
            logger.error(f"MPesa callback error: {e}")

        return Response({'ResultCode': 0, 'ResultDesc': 'Accepted'})


def _confirm_mpesa_booking(txn):
    """After successful M-Pesa payment, confirm the pending booking."""
    from apps.transport.models import Booking
    # Find the booking associated with this transaction
    # Transaction description stores: 'Trip booking #<id> | checkout:...'
    try:
        desc = txn.description
        booking_id = int(desc.split('Trip booking #')[1].split(' ')[0])
        booking = Booking.objects.get(id=booking_id, status=Booking.Status.PENDING)
        booking.status = Booking.Status.CONFIRMED
        booking.save()

        send_notification(
            recipient=txn.user,
            title='🎫 Booking Confirmed',
            body=f'Your M-Pesa payment was successful. Your trip seat is confirmed.',
            category='booking',
        )
    except Exception as e:
        logger.error(f"Could not confirm booking after M-Pesa payment: {e}")


class WalletTopUpSimulateView(APIView):
    """
    DEV ONLY: Simulate a successful M-Pesa top-up without real payment.
    Remove or gate behind DEBUG=True in production.
    """
    @transaction.atomic
    def post(self, request):
        from django.conf import settings
        if not settings.DEBUG:
            return Response({'error': 'Only available in development.'}, status=403)

        amount = request.data.get('amount', 100)
        try:
            profile = request.user.student_profile
            profile.wallet_balance += float(amount)
            profile.save()

            Transaction.objects.create(
                user=request.user,
                transaction_type=Transaction.TransactionType.WALLET_TOPUP,
                payment_method=Transaction.PaymentMethod.MPESA,
                amount=amount,
                status=Transaction.Status.SUCCESS,
                description=f'Simulated top-up of KES {amount}',
                phone_number=request.user.phone_number or '0700000000',
            )

            send_notification(
                recipient=request.user,
                title='💰 Wallet Topped Up (Dev)',
                body=f'KES {amount} added. Balance: KES {profile.wallet_balance}',
                category='payment',
            )

            return Response({
                'message': f'Wallet credited KES {amount}',
                'new_balance': str(profile.wallet_balance),
            })
        except Exception as e:
            return Response({'error': str(e)}, status=400)
