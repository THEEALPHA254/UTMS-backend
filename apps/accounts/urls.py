from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from .views import *

urlpatterns = [
    #auth
    path('login/', login_view, name='login'),
    path('users/', all_users, name='users'),
    path('users/create/', create_users, name='create_users'),
    path('users/<int:pk>/', user_detail, name='user-detail'),

    # Admin: students
    path('students/', studentList, name='student-list'),
    path('students/create/', create_students, name='create_students'),
    path('students/<int:pk>/', student_detail, name='student-detail'),
    # path('students/profiles/<int:pk>/status/', UpdateTransportStatusView.as_view(), name='transport-status'),
]
