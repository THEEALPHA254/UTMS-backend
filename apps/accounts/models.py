from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager
from django.db import models
from django.utils import timezone


class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('Email is required')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('role', User.Role.ADMIN)
        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    class Role(models.TextChoices):
        STUDENT = 'student', 'Student'
        STAFF = 'staff', 'Transport Staff'
        ADMIN = 'admin', 'Administrator'
        DRIVER = 'driver', 'Driver'

    email = models.EmailField(unique=True)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.STUDENT)
    phone_number = models.CharField(max_length=20, blank=True)
    profile_picture = models.ImageField(upload_to='profiles/', blank=True, null=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)

    objects = UserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['first_name', 'last_name']

    class Meta:
        db_table = 'users'

    def __str__(self):
        return f"{self.get_full_name()} ({self.email})"

    def get_full_name(self):
        return f"{self.first_name} {self.last_name}"


class StudentProfile(models.Model):
    class TransportStatus(models.TextChoices):
        ACTIVE = 'active', 'Active'
        INACTIVE = 'inactive', 'Inactive'
        SUSPENDED = 'suspended', 'Suspended'

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='student_profile')
    admission_number = models.CharField(max_length=50, unique=True)
    student_id = models.CharField(max_length=50, unique=True)
    faculty = models.CharField(max_length=100, blank=True)
    year_of_study = models.PositiveSmallIntegerField(default=1)
    transport_status = models.CharField(
        max_length=20,
        choices=TransportStatus.choices,
        default=TransportStatus.INACTIVE
    )
    wallet_balance = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    registered_at = models.DateTimeField(null=True, blank=True)

    # class Meta:
    #     db_table = 'student_profiles'

    def __str__(self):
        return f"{self.user.get_full_name()} - {self.admission_number}"


class DriverProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='driver_profile')
    license_number = models.CharField(max_length=50, unique=True)
    license_expiry = models.DateField()
    is_on_duty = models.BooleanField(default=False)

    class Meta:
        db_table = 'driver_profiles'

    def __str__(self):
        return f"Driver: {self.user.get_full_name()}"
