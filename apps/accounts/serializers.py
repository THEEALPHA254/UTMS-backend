# serializers.py
import secrets
import string
from rest_framework import serializers
from .models import *


# ── Helpers ───────────────────────────────────────────────────────────────────

def generate_password(length: int = 12) -> str:
    """
    Generate a secure random password.
    In dev, you can override this to return a fixed string for easy testing.
    """
    alphabet = string.ascii_letters + string.digits + "!@#$%"
    return "".join(secrets.choice(alphabet) for _ in range(length))


# ── Shared profile serializers ────────────────────────────────────────────────

class StudentProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = StudentProfile
        fields = [
            "id", "admission_number", "student_id", "faculty",
            "year_of_study", "transport_status", "wallet_balance", "registered_at",
        ]
        read_only_fields = ["wallet_balance", "registered_at"]


class DriverProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = DriverProfile
        fields = ["id", "license_number", "license_expiry", "is_on_duty"]
        read_only_fields = ["is_on_duty"]


# ── Shared user read serializer ───────────────────────────────────────────────

class UserSerializer(serializers.ModelSerializer):
    """
    Read-only. Used everywhere a user object needs to be returned.
    Includes nested profiles when present.
    """
    full_name       = serializers.SerializerMethodField()
    student_profile = StudentProfileSerializer(read_only=True)
    driver_profile  = DriverProfileSerializer(read_only=True)

    class Meta:
        model = User
        fields = [
            "id", "email", "first_name", "last_name", "full_name",
            "role", "phone_number", "profile_picture",
            "is_active", "date_joined",
            "student_profile", "driver_profile",
        ]
        read_only_fields = fields  # never write through this serializer

    def get_full_name(self, obj):
        return obj.get_full_name()


# ── Auth ──────────────────────────────────────────────────────────────────────

class LoginSerializer(serializers.Serializer):
    email    = serializers.EmailField()
    password = serializers.CharField()


# ── Staff-facing: create student ──────────────────────────────────────────────

class CreateStudentSerializer(serializers.Serializer):
    """
    Staff creates a student. User account is auto-created, credentials emailed.
    """
    # User fields
    email        = serializers.EmailField()
    first_name   = serializers.CharField(max_length=100)
    last_name    = serializers.CharField(max_length=100)
    phone_number = serializers.CharField(max_length=20, required=False, allow_blank=True)

    # Profile fields
    admission_number = serializers.CharField(max_length=50)
    student_id       = serializers.CharField(max_length=50)
    faculty          = serializers.CharField(max_length=100, required=False, allow_blank=True)
    year_of_study    = serializers.IntegerField(default=1, min_value=1, max_value=10)

    def validate_email(self, value):
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value

    def validate_admission_number(self, value):
        if StudentProfile.objects.filter(admission_number=value).exists():
            raise serializers.ValidationError("Admission number already registered.")
        return value

    def validate_student_id(self, value):
        if StudentProfile.objects.filter(student_id=value).exists():
            raise serializers.ValidationError("Student ID already registered.")
        return value

    def create(self, validated_data):
        profile_fields = {
            "admission_number": validated_data.pop("admission_number"),
            "student_id":       validated_data.pop("student_id"),
            "faculty":          validated_data.pop("faculty", ""),
            "year_of_study":    validated_data.pop("year_of_study", 1),
        }
        password = generate_password()
        user = User.objects.create_user(
            **validated_data,
            password=password,
            role=User.Role.STUDENT,
        )
        profile = StudentProfile.objects.create(user=user, **profile_fields)

        # Fire Celery task to email credentials
        from .tasks import send_credentials_email
        send_credentials_email.delay(user.email, user.get_full_name(), password, user.role)

        return profile


# ── Staff-facing: create driver ───────────────────────────────────────────────

class CreateDriverSerializer(serializers.Serializer):
    """
    Staff creates a driver. User account is auto-created, credentials emailed.
    """
    # User fields
    email        = serializers.EmailField()
    first_name   = serializers.CharField(max_length=100)
    last_name    = serializers.CharField(max_length=100)
    phone_number = serializers.CharField(max_length=20, required=False, allow_blank=True)

    # Profile fields
    license_number = serializers.CharField(max_length=50)
    license_expiry = serializers.DateField()

    def validate_email(self, value):
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value

    def validate_license_number(self, value):
        if DriverProfile.objects.filter(license_number=value).exists():
            raise serializers.ValidationError("License number already registered.")
        return value

    def create(self, validated_data):
        profile_fields = {
            "license_number": validated_data.pop("license_number"),
            "license_expiry": validated_data.pop("license_expiry"),
        }
        password = generate_password()
        user = User.objects.create_user(
            **validated_data,
            password=password,
            role=User.Role.DRIVER,
        )
        profile = DriverProfile.objects.create(user=user, **profile_fields)

        from .tasks import send_credentials_email
        send_credentials_email.delay(user.email, user.get_full_name(), password, user.role)

        return profile


# ── Admin-facing: create staff ────────────────────────────────────────────────

class CreateStaffSerializer(serializers.Serializer):
    """
    Admin creates another staff/admin user. Credentials are emailed.
    """
    email        = serializers.EmailField()
    first_name   = serializers.CharField(max_length=100)
    last_name    = serializers.CharField(max_length=100)
    phone_number = serializers.CharField(max_length=20, required=False, allow_blank=True)
    role         = serializers.ChoiceField(choices=[User.Role.STAFF, User.Role.ADMIN])

    def validate_email(self, value):
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value

    def create(self, validated_data):
        password = generate_password()
        user = User.objects.create_user(
            **validated_data,
            password=password,
            is_staff=True,  # grants Django admin access if needed
        )

        from .tasks import send_credentials_email
        send_credentials_email.delay(user.email, user.get_full_name(), password, user.role)

        return user


# ── Mobile self-registration: student ────────────────────────────────────────

class RegisterStudentSerializer(serializers.Serializer):
    """Mobile: student self-registers."""
    email            = serializers.EmailField()
    password         = serializers.CharField(write_only=True, min_length=8)
    first_name       = serializers.CharField(max_length=100)
    last_name        = serializers.CharField(max_length=100)
    phone_number     = serializers.CharField(max_length=20, required=False, allow_blank=True)
    admission_number = serializers.CharField(max_length=50)
    student_id       = serializers.CharField(max_length=50)
    faculty          = serializers.CharField(max_length=100, required=False, allow_blank=True)
    year_of_study    = serializers.IntegerField(default=1, min_value=1, max_value=10)

    def validate_email(self, value):
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("Email already registered.")
        return value

    def validate_admission_number(self, value):
        if StudentProfile.objects.filter(admission_number=value).exists():
            raise serializers.ValidationError("Admission number already registered.")
        return value

    def validate_student_id(self, value):
        if StudentProfile.objects.filter(student_id=value).exists():
            raise serializers.ValidationError("Student ID already registered.")
        return value

    def create(self, validated_data):
        profile_fields = {
            "admission_number": validated_data.pop("admission_number"),
            "student_id":       validated_data.pop("student_id"),
            "faculty":          validated_data.pop("faculty", ""),
            "year_of_study":    validated_data.pop("year_of_study", 1),
        }
        password = validated_data.pop("password")
        user = User.objects.create_user(
            **validated_data,
            password=password,
            role=User.Role.STUDENT,
        )
        StudentProfile.objects.create(user=user, **profile_fields)
        return user


# ── Mobile self-registration: driver ─────────────────────────────────────────

class RegisterDriverSerializer(serializers.Serializer):
    """Mobile: driver self-registers."""
    email          = serializers.EmailField()
    password       = serializers.CharField(write_only=True, min_length=8)
    first_name     = serializers.CharField(max_length=100)
    last_name      = serializers.CharField(max_length=100)
    phone_number   = serializers.CharField(max_length=20, required=False, allow_blank=True)
    license_number = serializers.CharField(max_length=50)
    license_expiry = serializers.DateField()

    def validate_email(self, value):
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("Email already registered.")
        return value

    def validate_license_number(self, value):
        if DriverProfile.objects.filter(license_number=value).exists():
            raise serializers.ValidationError("License number already registered.")
        return value

    def create(self, validated_data):
        profile_fields = {
            "license_number": validated_data.pop("license_number"),
            "license_expiry": validated_data.pop("license_expiry"),
        }
        password = validated_data.pop("password")
        user = User.objects.create_user(
            **validated_data,
            password=password,
            role=User.Role.DRIVER,
        )
        DriverProfile.objects.create(user=user, **profile_fields)
        return user


# ── Misc ──────────────────────────────────────────────────────────────────────

class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(required=True)
    new_password = serializers.CharField(required=True, min_length=8)

    def validate_old_password(self, value):
        user = self.context["request"].user
        if not user.check_password(value):
            raise serializers.ValidationError("Old password is incorrect.")
        return value