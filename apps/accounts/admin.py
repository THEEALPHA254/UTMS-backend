# Register your models here.
from django.contrib import admin

from .models import *
from import_export.admin import ImportExportModelAdmin

# Register your models here.

@admin.register(User)
class Users(ImportExportModelAdmin):
    list_display = ("email", "first_name",'password')

@admin.register(StudentProfile)
class ClientAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'admission_number', 'student_id', 'faculty', 'year_of_study'
                    ,'transport_status','wallet_balance','registered_at')
    search_fields = ('user', 'admission_number')
    ordering = ('-id',)
