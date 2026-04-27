# urls.py
from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from .views import *

urlpatterns = [
    # ── Auth ──────────────────────────────────────────────────────────────────
    path("login/", login_view,name="login"),
    path("token/refresh/", TokenRefreshView.as_view(), name="token-refresh"),

    # ── Students (staff/admin, web) ───────────────────────────────────────────
    path("students/", student_list,   name="student-list"),
    path("students/create/", create_student, name="student-create"),
    path("students/<int:pk>/", student_detail, name="student-detail"),

    # ── Drivers (staff/admin, web) ────────────────────────────────────────────
    path("drivers/", driver_list,   name="driver-list"),
    path("drivers/create/", create_driver, name="driver-create"),
    path("drivers/<int:pk>/", driver_detail, name="driver-detail"),

    # ── Staff management (admin only, web) ────────────────────────────────────
    path("staff/", staff_list,   name="staff-list"),
    path("staff/create/",  create_staff, name="staff-create"),
    path("staff/<int:pk>/", staff_detail, name="staff-detail"),

    # ── Mobile self-registration ──────────────────────────────────────────────
    path("register/student/", register_student, name="register-student"),
    path("register/driver/",  register_driver,  name="register-driver"),
]