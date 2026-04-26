from django.urls import path
from . import views

urlpatterns = [
    path('', views.MyNotificationsView.as_view(), name='my-notifications'),
    path('unread/', views.UnreadCountView.as_view(), name='unread-count'),
    path('<int:pk>/read/', views.MarkReadView.as_view(), name='mark-read'),
    path('read-all/', views.MarkAllReadView.as_view(), name='mark-all-read'),
]
