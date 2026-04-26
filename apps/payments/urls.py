from django.urls import path
from . import views

urlpatterns = [
    path('my/', views.MyTransactionsView.as_view(), name='my-transactions'),
    path('all/', views.AllTransactionsView.as_view(), name='all-transactions'),
    path('wallet/balance/', views.WalletBalanceView.as_view(), name='wallet-balance'),
    path('wallet/topup/', views.InitiateWalletTopUpView.as_view(), name='wallet-topup'),
    path('mpesa/callback/', views.MpesaCallbackView.as_view(), name='mpesa-callback'),
]
