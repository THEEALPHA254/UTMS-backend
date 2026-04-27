# views.py
from rest_framework import status
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import authenticate
from django.db.models import Q

from .models import *
from .serializers import *
from .permissions import *


# ── Helpers ───────────────────────────────────────────────────────────────────

class Pagination(PageNumberPagination):
    page_size = 15
    page_size_query_param = "page_size"
    max_page_size = 100

    def get_paginated_response(self, data):
        return Response({
            "success": True,
            "count":    self.page.paginator.count,
            "next":     self.get_next_link(),
            "previous": self.get_previous_link(),
            "results":  data,
        })


def ok(data=None, message="Success", status_code=status.HTTP_200_OK):
    return Response({"success": True, "message": message, "data": data}, status=status_code)


def fail(message="Error", errors=None, status_code=status.HTTP_400_BAD_REQUEST):
    return Response({"success": False, "message": message, "data": errors}, status=status_code)


# ── Auth ──────────────────────────────────────────────────────────────────────

@api_view(["POST"])
@authentication_classes([])
@permission_classes([])
def login_view(request):
    """
    Login endpoint shared by all roles.
    Returns the user's role so the frontend can gate web access.
    Non-staff users (students/drivers) will receive role='student'/'driver'
    — the frontend is responsible for blocking them from the web UI.
    """
    serializer = LoginSerializer(data=request.data)
    if not serializer.is_valid():
        return fail("Validation failed", serializer.errors)

    user = authenticate(
        request,
        username=serializer.validated_data["email"],
        password=serializer.validated_data["password"],
    )
    if user is None:
        return fail("Invalid email or password.", status_code=status.HTTP_401_UNAUTHORIZED)

    if not user.is_active:
        return fail("Account is deactivated.", status_code=status.HTTP_403_FORBIDDEN)

    refresh = RefreshToken.for_user(user)
    return ok({
        **UserSerializer(user).data,
        "access":  str(refresh.access_token),
        "refresh": str(refresh),
    }, message="Login successful")


# ── Students (staff-facing, web) ──────────────────────────────────────────────

@api_view(["GET"])
@permission_classes([IsStaffOrAdmin])
def student_list(request):
    """List all students with search + filter. Staff/Admin only."""
    qs = StudentProfile.objects.select_related("user").order_by("id")

    search = request.query_params.get("search")
    if search:
        qs = qs.filter(
            Q(user__first_name__icontains=search) |
            Q(user__last_name__icontains=search)  |
            Q(user__email__icontains=search)       |
            Q(admission_number__icontains=search)
        )

    transport_status = request.query_params.get("transport_status")
    if transport_status:
        qs = qs.filter(transport_status=transport_status)

    is_active = request.query_params.get("is_active")
    if is_active is not None:
        qs = qs.filter(user__is_active=is_active.lower() == "true")

    paginator = Pagination()
    page = paginator.paginate_queryset(qs, request)
    return paginator.get_paginated_response(UserSerializer([s.user for s in page], many=True).data)


@api_view(["POST"])
@permission_classes([IsStaffOrAdmin])
def create_student(request):
    """Staff creates a student. Credentials are emailed automatically."""
    serializer = CreateStudentSerializer(data=request.data)
    if not serializer.is_valid():
        return fail("Student creation failed", serializer.errors)
    profile = serializer.save()
    return ok(UserSerializer(profile.user).data, "Student created. Credentials sent by email.", status.HTTP_201_CREATED)


@api_view(["GET", "PUT", "DELETE"])
@permission_classes([IsStaffOrAdmin])
def student_detail(request, pk):
    try:
        profile = StudentProfile.objects.select_related("user").get(pk=pk)
    except StudentProfile.DoesNotExist:
        return fail("Student not found", status_code=status.HTTP_404_NOT_FOUND)

    if request.method == "GET":
        return ok(UserSerializer(profile.user).data)

    if request.method == "PUT":
        # Update profile fields only
        serializer = StudentProfileSerializer(profile, data=request.data, partial=True)
        if not serializer.is_valid():
            return fail("Update failed", serializer.errors)
        serializer.save()
        return ok(UserSerializer(profile.user).data, "Student updated successfully")

    if request.method == "DELETE":
        profile.user.delete()  # CASCADE deletes profile too
        return Response({"success": True, "message": "Student deleted."}, status=status.HTTP_204_NO_CONTENT)


# ── Drivers (staff-facing, web) ───────────────────────────────────────────────

@api_view(["GET"])
@permission_classes([IsStaffOrAdmin])
def driver_list(request):
    """List all drivers. Staff/Admin only."""
    qs = DriverProfile.objects.select_related("user").order_by("id")

    search = request.query_params.get("search")
    if search:
        qs = qs.filter(
            Q(user__first_name__icontains=search) |
            Q(user__last_name__icontains=search)  |
            Q(user__email__icontains=search)
        )

    paginator = Pagination()
    page = paginator.paginate_queryset(qs, request)
    return paginator.get_paginated_response(UserSerializer([d.user for d in page], many=True).data)


@api_view(["POST"])
@permission_classes([IsStaffOrAdmin])
def create_driver(request):
    """Staff creates a driver. Credentials are emailed automatically."""
    serializer = CreateDriverSerializer(data=request.data)
    if not serializer.is_valid():
        return fail("Driver creation failed", serializer.errors)
    profile = serializer.save()
    return ok(UserSerializer(profile.user).data, "Driver created. Credentials sent by email.", status.HTTP_201_CREATED)


@api_view(["GET", "PUT", "DELETE"])
@permission_classes([IsStaffOrAdmin])
def driver_detail(request, pk):
    try:
        profile = DriverProfile.objects.select_related("user").get(pk=pk)
    except DriverProfile.DoesNotExist:
        return fail("Driver not found", status_code=status.HTTP_404_NOT_FOUND)

    if request.method == "GET":
        return ok(UserSerializer(profile.user).data)

    if request.method == "PUT":
        serializer = DriverProfileSerializer(profile, data=request.data, partial=True)
        if not serializer.is_valid():
            return fail("Update failed", serializer.errors)
        serializer.save()
        return ok(UserSerializer(profile.user).data, "Driver updated successfully")

    if request.method == "DELETE":
        profile.user.delete()
        return Response({"success": True, "message": "Driver deleted."}, status=status.HTTP_204_NO_CONTENT)


# ── Staff management (admin-only, web) ───────────────────────────────────────

@api_view(["GET"])
@permission_classes([IsAdminRole])
def staff_list(request):
    """
    Admin can list staff accounts.
    Admins cannot see other admins — only role=staff users are returned.
    """
    qs = User.objects.filter(role=User.Role.STAFF).order_by("id")

    search = request.query_params.get("search")
    if search:
        qs = qs.filter(
            Q(first_name__icontains=search) |
            Q(last_name__icontains=search)  |
            Q(email__icontains=search)
        )

    paginator = Pagination()
    page = paginator.paginate_queryset(qs, request)
    return paginator.get_paginated_response(UserSerializer(page, many=True).data)


@api_view(["POST"])
@permission_classes([IsAdminRole])
def create_staff(request):
    """Admin creates a new staff or admin account. Credentials are emailed."""
    serializer = CreateStaffSerializer(data=request.data)
    if not serializer.is_valid():
        return fail("Staff creation failed", serializer.errors)
    user = serializer.save()
    return ok(UserSerializer(user).data, "Staff account created. Credentials sent by email.", status.HTTP_201_CREATED)


@api_view(["GET", "PUT", "DELETE"])
@permission_classes([IsAdminRole])
def staff_detail(request, pk):
    try:
        # Admins can only manage staff-role users, not other admins
        user = User.objects.get(pk=pk, role=User.Role.STAFF)
    except User.DoesNotExist:
        return fail("Staff member not found", status_code=status.HTTP_404_NOT_FOUND)

    if request.method == "GET":
        return ok(UserSerializer(user).data)

    if request.method == "PUT":
        allowed_fields = {"first_name", "last_name", "phone_number", "is_active"}
        data = {k: v for k, v in request.data.items() if k in allowed_fields}
        for attr, value in data.items():
            setattr(user, attr, value)
        user.save()
        return ok(UserSerializer(user).data, "Staff updated successfully")

    if request.method == "DELETE":
        user.delete()
        return Response({"success": True, "message": "Staff deleted."}, status=status.HTTP_204_NO_CONTENT)


# ── Mobile: self-registration ─────────────────────────────────────────────────

@api_view(["POST"])
@authentication_classes([])
@permission_classes([])
def register_student(request):
    """Mobile app: student self-registers."""
    serializer = RegisterStudentSerializer(data=request.data)
    if not serializer.is_valid():
        return fail("Registration failed", serializer.errors)
    user = serializer.save()
    refresh = RefreshToken.for_user(user)
    return ok({
        **UserSerializer(user).data,
        "access":  str(refresh.access_token),
        "refresh": str(refresh),
    }, "Student registered successfully", status.HTTP_201_CREATED)


@api_view(["POST"])
@authentication_classes([])
@permission_classes([])
def register_driver(request):
    """Mobile app: driver self-registers."""
    serializer = RegisterDriverSerializer(data=request.data)
    if not serializer.is_valid():
        return fail("Registration failed", serializer.errors)
    user = serializer.save()
    refresh = RefreshToken.for_user(user)
    return ok({
        **UserSerializer(user).data,
        "access":  str(refresh.access_token),
        "refresh": str(refresh),
    }, "Driver registered successfully", status.HTTP_201_CREATED)