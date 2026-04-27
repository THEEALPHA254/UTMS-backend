from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from import_export.admin import ImportExportModelAdmin
from .models import *


# ── User ──────────────────────────────────────────────────────────────────────
@admin.register(User)
class UserAdmin(ImportExportModelAdmin, BaseUserAdmin):
    list_display  = ('email', 'first_name', 'last_name', 'role', 'phone_number', 'is_active', 'is_staff', 'date_joined')
    list_filter   = ('role', 'is_active', 'is_staff')
    search_fields = ('email', 'first_name', 'last_name', 'phone_number')
    ordering      = ('-date_joined',)
    readonly_fields = ('date_joined', 'last_login')

    # Fieldsets control the layout on the change/add pages
    fieldsets = (
        ('Credentials',  {'fields': ('email', 'password')}),
        ('Personal Info', {'fields': ('first_name', 'last_name', 'phone_number', 'profile_picture')}),
        ('Role & Status', {'fields': ('role', 'is_active', 'is_staff', 'is_superuser')}),
        ('Permissions',   {'fields': ('groups', 'user_permissions'), 'classes': ('collapse',)}),
        ('Timestamps',    {'fields': ('date_joined', 'last_login'), 'classes': ('collapse',)}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields':  ('email', 'first_name', 'last_name', 'role', 'password1', 'password2'),
        }),
    )

    # Switch from username to email as the identifier
    USERNAME_FIELD = 'email'


# ── StudentProfile ────────────────────────────────────────────────────────────
@admin.register(StudentProfile)
class StudentProfileAdmin(ImportExportModelAdmin):
    list_display   = ('id', 'full_name', 'email', 'admission_number', 'student_id',
                      'faculty', 'year_of_study', 'transport_status', 'wallet_balance', 'registered_at')
    list_filter    = ('transport_status', 'year_of_study', 'faculty')
    search_fields  = ('user__first_name', 'user__last_name', 'user__email',
                      'admission_number', 'student_id')
    ordering       = ('-id',)
    readonly_fields = ('registered_at',)

    fieldsets = (
        ('Linked Account', {'fields': ('user',)}),
        ('Academic Info',  {'fields': ('admission_number', 'student_id', 'faculty', 'year_of_study')}),
        ('Transport',      {'fields': ('transport_status', 'wallet_balance')}),
        ('Timestamps',     {'fields': ('registered_at',), 'classes': ('collapse',)}),
    )

    # Computed columns for list_display
    @admin.display(description='Full Name', ordering='user__first_name')
    def full_name(self, obj):
        return obj.user.get_full_name()

    @admin.display(description='Email', ordering='user__email')
    def email(self, obj):
        return obj.user.email


# ── DriverProfile ─────────────────────────────────────────────────────────────
@admin.register(DriverProfile)
class DriverProfileAdmin(ImportExportModelAdmin):
    list_display  = ('id', 'full_name', 'email', 'license_number', 'license_expiry', 'is_on_duty')
    list_filter   = ('is_on_duty',)
    search_fields = ('user__first_name', 'user__last_name', 'user__email', 'license_number')
    ordering      = ('user__first_name',)

    fieldsets = (
        ('Linked Account', {'fields': ('user',)}),
        ('License',        {'fields': ('license_number', 'license_expiry')}),
        ('Duty Status',    {'fields': ('is_on_duty',)}),
    )

    @admin.display(description='Full Name', ordering='user__first_name')
    def full_name(self, obj):
        return obj.user.get_full_name()

    @admin.display(description='Email', ordering='user__email')
    def email(self, obj):
        return obj.user.email