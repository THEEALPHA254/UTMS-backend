from django.contrib import admin
from .models import Transaction


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display  = ('id', 'reference', 'user', 'transaction_type', 'payment_method',
                     'amount', 'status', 'phone_number', 'external_ref', 'created_at')
    list_filter   = ('status', 'transaction_type', 'payment_method')
    search_fields = ('reference', 'external_ref', 'user__email',
                     'user__first_name', 'user__last_name', 'phone_number')
    ordering      = ('-created_at',)
    readonly_fields = ('reference', 'created_at', 'updated_at')
    raw_id_fields = ('user',)
    date_hierarchy = 'created_at'

    fieldsets = (
        ('Transaction',  {'fields': ('user', 'transaction_type', 'payment_method', 'amount', 'status')}),
        ('References',   {'fields': ('reference', 'external_ref', 'phone_number', 'description')}),
        ('Timestamps',   {'fields': ('created_at', 'updated_at'), 'classes': ('collapse',)}),
    )
