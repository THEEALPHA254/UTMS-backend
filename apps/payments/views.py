from rest_framework import generics, status, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from django.db import transaction
from django.utils import timezone
from .models import Transaction
from .mpesa import stk_push
from apps.accounts.serializers import TopUpWalletSerializer
from apps.accounts.models import StudentProfile
import logging

logger = logging.getLogger(__name__)


class TransactionSerializer(generics.ListAPIView):
    pass


from rest_framework import serializers as drf_serializers


class TxnSerializer(drf_serializers.ModelSerializer):
    class Meta:
        model = Transaction
        fields = '__all__'


class MyTransactionsView(generics.ListAPIView):
    """Student: view own transaction history."""
    serializer_class = TxnSerializer

    def get_queryset(self):
        return Transaction.objects.filter(user=self.request.user)


class AllTransactionsView(generics.ListAPIView):
    """Admin: view all transactions."""
    serializer_class = TxnSerializer
    permission_classes = [permissions.IsAdminUser]
    queryset = Transaction.objects.select_related('user').all()
    filterset_fields = ['status', 'transaction_type', 'payment_method']
    search_fields = ['user__email', 'reference', 'external_ref']


class InitiateWalletTopUpView(APIView):
    """
    Student initiates a wallet top-up.
    For MPesa: triggers STK Push, returns CheckoutRequestID.
    For card: placeholder (integrate Stripe/Flutterwave as needed).
    """

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
            if not phone:
                return Response({'error': 'Phone number required for M-Pesa.'}, status=400)
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
                    'message': 'STK Push sent. Please complete payment on your phone.',
                    'reference': txn.reference,
                    'checkout_request_id': txn.external_ref,
                })
            except Exception as e:
                txn.status = Transaction.Status.FAILED
                txn.save()
                logger.error(f"MPesa STK Push failed: {e}")
                return Response({'error': 'M-Pesa request failed. Try again.'}, status=502)

        # Card — return pending transaction for further processing
        return Response({
            'message': 'Transaction initiated.',
            'reference': txn.reference,
            'amount': str(data['amount']),
        })


class MpesaCallbackView(APIView):
    """
    Safaricom callback endpoint. Called by Safaricom after STK Push completes.
    No authentication required (Safaricom calls this directly).
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
                # Success
                txn.status = Transaction.Status.SUCCESS
                txn.save()
                # Credit wallet
                profile = StudentProfile.objects.get(user=txn.user)
                profile.wallet_balance += txn.amount
                profile.save()
                logger.info(f"Wallet topped up: {txn.user} +KES{txn.amount}")
            else:
                txn.status = Transaction.Status.FAILED
                txn.save()
                logger.warning(f"MPesa payment failed for {txn.reference}: code {result_code}")

        except Transaction.DoesNotExist:
            logger.error(f"No transaction found for CheckoutRequestID: {checkout_id}")
        except Exception as e:
            logger.error(f"MPesa callback error: {e}")

        # Always return 200 to Safaricom
        return Response({'ResultCode': 0, 'ResultDesc': 'Accepted'})


class WalletBalanceView(APIView):
    """Student: check wallet balance."""
    def get(self, request):
        try:
            profile = request.user.student_profile
            return Response({
                'balance': str(profile.wallet_balance),
                'currency': 'KES',
            })
        except Exception:
            return Response({'error': 'Student profile not found.'}, status=404)
