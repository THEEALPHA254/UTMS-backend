from django.urls import path
from . import views

urlpatterns = [
    # Student
    path('my/', views.MyTransactionsView.as_view(), name='my-transactions'),
    path('wallet/balance/', views.WalletBalanceView.as_view(), name='wallet-balance'),
    path('wallet/topup/', views.InitiateWalletTopUpView.as_view(), name='wallet-topup'),
    # Dev only — simulate top-up without real M-Pesa
    path('wallet/simulate-topup/', views.WalletTopUpSimulateView.as_view(), name='wallet-simulate'),
    # Admin
    path('all/', views.AllTransactionsView.as_view(), name='all-transactions'),
    # M-Pesa callback (called by Safaricom)
    path('mpesa/callback/', views.MpesaCallbackView.as_view(), name='mpesa-callback'),
]
