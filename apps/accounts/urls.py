from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from .views import *

urlpatterns = [
    # Auth
    path('register/', RegisterStudentView.as_view(), name='register'),
    path('login/', TokenObtainPairView.as_view(), name='login'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token-refresh'),
    path('logout/', LogoutView.as_view(), name='logout'),
    # Profile
    path('me/', CurrentUserView.as_view(), name='current-user'),
    path('change-password/', ChangePasswordView.as_view(), name='change-password'),
    # Admin: students
    # path('students/', views.StudentListView.as_view(), name='student-list'),
    path('students/create/', create_students, name='create_students'),
    path('students/<int:pk>/', StudentDetailView.as_view(), name='student-detail'),
    path('students/profiles/<int:pk>/status/', UpdateTransportStatusView.as_view(), name='transport-status'),
]
