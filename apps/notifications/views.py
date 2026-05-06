from rest_framework import generics, serializers as drf_serializers
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import permissions
from .models import Notification


class NotificationSerializer(drf_serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = '__all__'
        read_only_fields = ['recipient', 'created_at']


class MyNotificationsView(generics.ListAPIView):
    """User: list own notifications, newest first."""
    serializer_class = NotificationSerializer

    def get_queryset(self):
        qs = Notification.objects.filter(recipient=self.request.user)
        # Optional filter: ?unread=true
        unread = self.request.query_params.get('unread')
        if unread and unread.lower() == 'true':
            qs = qs.filter(is_read=False)
        return qs


class MarkReadView(APIView):
    """Mark a single notification as read."""
    def post(self, request, pk):
        # pk=-1 is a sentinel used by mobile app to mark all read
        if str(pk) == '-1':
            Notification.objects.filter(
                recipient=request.user, is_read=False
            ).update(is_read=True)
            return Response({'status': 'all marked read'})
        try:
            notif = Notification.objects.get(pk=pk, recipient=request.user)
            notif.is_read = True
            notif.save()
            return Response({'status': 'marked read'})
        except Notification.DoesNotExist:
            return Response({'error': 'Not found'}, status=404)


class MarkAllReadView(APIView):
    """Mark all notifications as read."""
    def post(self, request):
        Notification.objects.filter(
            recipient=request.user, is_read=False
        ).update(is_read=True)
        return Response({'status': 'all marked read'})


class UnreadCountView(APIView):
    """Return count of unread notifications."""
    def get(self, request):
        count = Notification.objects.filter(
            recipient=request.user, is_read=False
        ).count()
        return Response({'unread': count})


class DeleteNotificationView(APIView):
    """Delete a specific notification."""
    def delete(self, request, pk):
        try:
            notif = Notification.objects.get(pk=pk, recipient=request.user)
            notif.delete()
            return Response({'status': 'deleted'})
        except Notification.DoesNotExist:
            return Response({'error': 'Not found'}, status=404)
