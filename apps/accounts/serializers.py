from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import StudentProfile, DriverProfile
from rest_framework import serializers
from .models import *

class LoginSerializer(serializers.Serializer):
    email    = serializers.EmailField()
    password = serializers.CharField()

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model  = User
        fields = '__all__'


class StudentProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = StudentProfile
        fields = [
            'id', 'admission_number', 'student_id', 'faculty',
            'year_of_study', 'transport_status', 'wallet_balance', 'registered_at'
        ]
        read_only_fields = ['wallet_balance', 'transport_status', 'registered_at']


class StudentSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True) 

    class Meta:
        model = StudentProfile
        fields = '__all__'

class DriverProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = DriverProfile
        fields = ['id', 'license_number', 'license_expiry', 'is_on_duty']


class UserSerializer(serializers.ModelSerializer):
    student_profile = StudentProfileSerializer(read_only=True)
    driver_profile = DriverProfileSerializer(read_only=True)
    full_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'email', 'first_name', 'last_name', 'full_name',
            'role', 'phone_number', 'profile_picture', 'is_active',
            'date_joined', 'student_profile', 'driver_profile'
        ]
        read_only_fields = ['date_joined', 'is_active']

    def get_full_name(self, obj):
        return obj.get_full_name()


class RegisterStudentSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)
    admission_number = serializers.CharField()
    student_id = serializers.CharField()
    faculty = serializers.CharField(required=False, allow_blank=True)
    year_of_study = serializers.IntegerField(default=1)

    class Meta:
        model = User
        fields = [
            'email', 'password', 'first_name', 'last_name',
            'phone_number', 'admission_number', 'student_id',
            'faculty', 'year_of_study'
        ]

    def validate_admission_number(self, value):
        if StudentProfile.objects.filter(admission_number=value).exists():
            raise serializers.ValidationError("Admission number already registered.")
        return value

    def validate_student_id(self, value):
        if StudentProfile.objects.filter(student_id=value).exists():
            raise serializers.ValidationError("Student ID already registered.")
        return value

    def create(self, validated_data):
        profile_data = {
            'admission_number': validated_data.pop('admission_number'),
            'student_id': validated_data.pop('student_id'),
            'faculty': validated_data.pop('faculty', ''),
            'year_of_study': validated_data.pop('year_of_study', 1),
        }
        user = User.objects.create_user(**validated_data, role=User.Role.STUDENT)
        StudentProfile.objects.create(user=user, **profile_data)
        return user


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(required=True)
    new_password = serializers.CharField(required=True, min_length=8)

    def validate_old_password(self, value):
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError("Old password is incorrect.")
        return value


class TopUpWalletSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=10)
    payment_method = serializers.ChoiceField(choices=['mpesa', 'card'])
    phone_number = serializers.CharField(required=False)  # for MPesa
