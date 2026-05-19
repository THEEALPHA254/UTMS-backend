from django.contrib import admin
from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display  = ('id', 'recipient', 'title', 'category', 'is_read', 'created_at')
    list_filter   = ('category', 'is_read')
    search_fields = ('recipient__email', 'recipient__first_name', 'title', 'body')
    ordering      = ('-created_at',)
    readonly_fields = ('created_at',)
    raw_id_fields = ('recipient',)
    date_hierarchy = 'created_at'
    list_editable = ('is_read',)
