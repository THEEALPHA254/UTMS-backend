import csv
from rest_framework import generics, status, permissions
from rest_framework.pagination import PageNumberPagination
from rest_framework.views import APIView
from rest_framework.response import Response
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse
from django.utils import timezone
from .models import Transaction
from .mpesa import stk_push, query_stk_status
from apps.accounts.models import StudentProfile
from apps.accounts.permissions import IsStaffOrAdmin
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
    student_admission = drf_serializers.SerializerMethodField()
    student_name = drf_serializers.SerializerMethodField()

    class Meta:
        model = Transaction
        fields = '__all__'

    def get_student_admission(self, obj):
        try:
            return obj.user.student_profile.admission_number
        except Exception:
            return None

    def get_student_name(self, obj):
        return obj.user.get_full_name()


class TopUpWalletSerializer(drf_serializers.Serializer):
    amount = drf_serializers.DecimalField(max_digits=10, decimal_places=2, min_value=10)
    payment_method = drf_serializers.ChoiceField(choices=['mpesa'])
    phone_number = drf_serializers.CharField(required=False, allow_blank=True)

    def validate(self, data):
        if not data.get('phone_number'):
            raise drf_serializers.ValidationError(
                {'phone_number': 'Phone number is required for M-Pesa.'}
            )
        return data


class TxnPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 200

    def get_paginated_response(self, data):
        return Response({
            'count': self.page.paginator.count,
            'next': self.get_next_link(),
            'previous': self.get_previous_link(),
            'results': data,
        })


# ── Views ─────────────────────────────────────────────────────────────────────

class MyTransactionsView(generics.ListAPIView):
    """Student/Driver: view own transaction history."""
    serializer_class = TxnSerializer

    def get_queryset(self):
        return Transaction.objects.filter(
            user=self.request.user
        ).order_by('-created_at')


class AllTransactionsView(APIView):
    """Admin/Staff: view all transactions with filtering, pagination, and CSV export."""
    permission_classes = [IsStaffOrAdmin]

    def get(self, request):
        qs = Transaction.objects.select_related('user__student_profile').order_by('-created_at')

        payment_method = request.query_params.get('payment_method')
        if payment_method:
            qs = qs.filter(payment_method=payment_method)

        txn_status = request.query_params.get('status')
        if txn_status:
            qs = qs.filter(status=txn_status)

        txn_type = request.query_params.get('transaction_type')
        if txn_type:
            qs = qs.filter(transaction_type=txn_type)

        search = request.query_params.get('search')
        if search:
            qs = qs.filter(
                Q(user__email__icontains=search) |
                Q(reference__icontains=search) |
                Q(user__student_profile__admission_number__icontains=search)
            )

        date_from = request.query_params.get('date_from')
        date_to = request.query_params.get('date_to')
        if date_from:
            qs = qs.filter(created_at__date__gte=date_from)
        if date_to:
            qs = qs.filter(created_at__date__lte=date_to)

        # CSV export
        if request.query_params.get('format') == 'csv' or request.query_params.get('export') == 'csv':
            response = HttpResponse(content_type='text/csv')
            response['Content-Disposition'] = 'attachment; filename="payments.csv"'
            writer = csv.writer(response)
            writer.writerow(['Reference', 'Admission No', 'Student Name', 'Method', 'Type', 'Amount', 'Status', 'Date'])
            for t in qs:
                try:
                    admission = t.user.student_profile.admission_number
                except Exception:
                    admission = ''
                writer.writerow([
                    t.reference,
                    admission,
                    t.user.get_full_name(),
                    t.payment_method,
                    t.transaction_type,
                    t.amount,
                    t.status,
                    t.created_at.strftime('%Y-%m-%d %H:%M'),
                ])
            return response

        paginator = TxnPagination()
        page = paginator.paginate_queryset(qs, request)
        serializer = TxnSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


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
    """Student initiates a wallet top-up via M-Pesa STK Push."""
    @transaction.atomic
    def post(self, request):
        serializer = TopUpWalletSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        phone = data.get('phone_number') or request.user.phone_number
        txn = Transaction.objects.create(
            user=request.user,
            transaction_type=Transaction.TransactionType.WALLET_TOPUP,
            payment_method=Transaction.PaymentMethod.MPESA,
            amount=data['amount'],
            status=Transaction.Status.PENDING,
            phone_number=phone,
            description=f"Wallet top-up of KES {data['amount']}",
        )

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
    try:
        # Primary lookup: use the transaction reference stored on the booking via description
        # Format: 'Trip booking #<id> | checkout:<checkout_id>'
        # Fall back to scanning all pending bookings linked to this user + trip reference
        booking = None
        desc = txn.description or ''
        if 'Trip booking #' in desc:
            try:
                booking_id = int(desc.split('Trip booking #')[1].split(' ')[0].split('|')[0].strip())
                booking = Booking.objects.get(id=booking_id, status=Booking.Status.PENDING)
            except (ValueError, Booking.DoesNotExist):
                booking = None

        if booking is None:
            # Fallback: find any pending booking by this user created around the same time
            booking = Booking.objects.filter(
                student=txn.user, status=Booking.Status.PENDING
            ).order_by('-created_at').first()

        if booking is None:
            logger.error(f"No pending booking found for transaction {txn.reference}")
            return

        booking.status = Booking.Status.CONFIRMED
        booking.save()

        send_notification(
            recipient=txn.user,
            title='🎫 Booking Confirmed',
            body='Your M-Pesa payment was successful. Your trip seat is confirmed.',
            category='booking',
        )
    except Exception as e:
        logger.error(f"Could not confirm booking after M-Pesa payment: {e}")


class MpesaQueryView(APIView):
    """
    Student: manually check whether their pending M-Pesa top-up has been paid.
    Use this when the automatic callback hasn't fired (e.g. local dev without a
    public callback URL).  Pass the transaction reference returned by /wallet/topup/.
    """
    @transaction.atomic
    def post(self, request):
        reference = request.data.get('reference', '').strip()
        if not reference:
            return Response({'error': 'reference is required.'}, status=400)

        try:
            txn = Transaction.objects.select_for_update().get(
                reference=reference, user=request.user
            )
        except Transaction.DoesNotExist:
            return Response({'error': 'Transaction not found.'}, status=404)

        # Already processed — just return current balance
        if txn.status == Transaction.Status.SUCCESS:
            profile = request.user.student_profile
            return Response({
                'status': 'success',
                'message': 'Payment already confirmed.',
                'balance': str(profile.wallet_balance),
            })

        if txn.status == Transaction.Status.FAILED:
            return Response({'status': 'failed', 'message': 'Payment failed or was cancelled.'})

        if not txn.external_ref:
            return Response({'error': 'No M-Pesa request found for this transaction.'}, status=400)

        try:
            result = query_stk_status(txn.external_ref)
        except Exception as e:
            logger.error(f"STK query failed for {txn.reference}: {e}")
            return Response({'error': 'Could not reach M-Pesa. Try again shortly.'}, status=502)

        result_code = str(result.get('ResultCode', ''))

        if result_code == '0':
            txn.status = Transaction.Status.SUCCESS
            txn.save()

            profile = StudentProfile.objects.get(user=txn.user)
            profile.wallet_balance += txn.amount
            profile.save()
            logger.info(f"Wallet topped up via query: {txn.user} +KES{txn.amount}")

            send_notification(
                recipient=txn.user,
                title='💰 Wallet Topped Up',
                body=f'KES {txn.amount} has been added to your wallet. New balance: KES {profile.wallet_balance}',
                category='payment',
            )
            return Response({
                'status': 'success',
                'message': f'KES {txn.amount} added to your wallet.',
                'balance': str(profile.wallet_balance),
            })

        # Map common Safaricom result codes to friendly messages
        _messages = {
            '1032': 'Payment was cancelled on your phone.',
            '1': 'Insufficient M-Pesa balance.',
            '1037': 'Payment timed out. Please try again.',
            '2001': 'Invalid initiator information.',
        }
        msg = _messages.get(result_code, f'Payment not completed (code {result_code}).')

        # Mark as failed for terminal codes (not still-pending)
        if result_code not in ('', None):
            txn.status = Transaction.Status.FAILED
            txn.save()

        return Response({'status': 'failed', 'message': msg})


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
