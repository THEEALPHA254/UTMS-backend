# views.py
from rest_framework import generics, serializers as drf_serializers
from rest_framework.views import APIView
from rest_framework.response import Response
from .models import Notification


class NotificationSerializer(drf_serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = '__all__'
        read_only_fields = ['recipient', 'created_at']


class MyNotificationsView(generics.ListAPIView):
    serializer_class = NotificationSerializer

    def get_queryset(self):
        return Notification.objects.filter(recipient=self.request.user)


class MarkReadView(APIView):
    def post(self, request, pk):
        try:
            notif = Notification.objects.get(pk=pk, recipient=request.user)
            notif.is_read = True
            notif.save()
            return Response({'status': 'marked read'})
        except Notification.DoesNotExist:
            return Response({'error': 'Not found'}, status=404)


class MarkAllReadView(APIView):
    def post(self, request):
        Notification.objects.filter(recipient=request.user, is_read=False).update(is_read=True)
        return Response({'status': 'all marked read'})


class UnreadCountView(APIView):
    def get(self, request):
        count = Notification.objects.filter(recipient=request.user, is_read=False).count()
        return Response({'unread': count})
