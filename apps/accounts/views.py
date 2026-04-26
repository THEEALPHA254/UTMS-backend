from rest_framework import generics, status, permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import get_user_model
from .serializers import *
from .models import *
from rest_framework.decorators import api_view
from rest_framework.decorators import authentication_classes, permission_classes

User = get_user_model()


class RegisterStudentView(generics.CreateAPIView):
    """Student self-registration endpoint."""
    serializer_class = RegisterStudentSerializer
    permission_classes = [permissions.AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        tokens = self._get_tokens(user)
        return Response({
            'message': 'Registration successful.',
            'user': UserSerializer(user).data,
            **tokens
        }, status=status.HTTP_201_CREATED)

    def _get_tokens(self, user):
        refresh = RefreshToken.for_user(user)
        return {
            'access': str(refresh.access_token),
            'refresh': str(refresh),
        }


class CurrentUserView(generics.RetrieveUpdateAPIView):
    """Get or update the currently authenticated user."""
    serializer_class = UserSerializer

    def get_object(self):
        return self.request.user


class ChangePasswordView(APIView):
    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        request.user.set_password(serializer.validated_data['new_password'])
        request.user.save()
        return Response({'message': 'Password updated successfully.'})


class StudentListView(generics.ListAPIView):
    """Admin: list all students."""
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAdminUser]
    queryset = User.objects.filter(role='student').select_related('student_profile')
    search_fields = ['email', 'first_name', 'last_name', 'student_profile__admission_number']
    filterset_fields = ['is_active', 'student_profile__transport_status']

@api_view(["POST"])
@authentication_classes([])
@permission_classes([])
def create_students(request):
    serializer = StudentSerializer(data=request.data)
    if serializer.is_valid():
        serializer.save()
        response_data = {
            "success": True,
            "message": "Student created successfully",
            "data": serializer.data,
        }
        return Response(response_data, status=status.HTTP_201_CREATED)
    response_data = {
        "success": False,
        "message": "Student creation failed",
        "data": serializer.errors,
    }
    return Response(response_data, status=status.HTTP_400_BAD_REQUEST)

class StudentDetailView(generics.RetrieveUpdateAPIView):
    """Admin: retrieve or update a student."""
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAdminUser]
    queryset = User.objects.filter(role='student').select_related('student_profile')


class UpdateTransportStatusView(APIView):
    """Admin: activate/deactivate/suspend a student's transport."""
    permission_classes = [permissions.IsAdminUser]

    def patch(self, request, pk):
        try:
            profile = StudentProfile.objects.get(pk=pk)
        except StudentProfile.DoesNotExist:
            return Response({'error': 'Student profile not found.'}, status=404)
        new_status = request.data.get('transport_status')
        if new_status not in [c[0] for c in StudentProfile.TransportStatus.choices]:
            return Response({'error': 'Invalid status.'}, status=400)
        profile.transport_status = new_status
        profile.save()
        return Response(StudentProfileSerializer(profile).data)


class LogoutView(APIView):
    """Blacklist the refresh token on logout."""
    def post(self, request):
        try:
            token = RefreshToken(request.data['refresh'])
            token.blacklist()
            return Response({'message': 'Logged out successfully.'})
        except Exception:
            return Response({'error': 'Invalid token.'}, status=400)
