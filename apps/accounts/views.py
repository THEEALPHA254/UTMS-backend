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
from rest_framework.status import HTTP_200_OK, HTTP_400_BAD_REQUEST
from django.contrib.auth import authenticate
from rest_framework.pagination import PageNumberPagination
from django.db.models import Q



class StudentPagination(PageNumberPagination):
    page_size = 15
    page_size_query_param = 'page_size'
    max_page_size = 100

    def get_paginated_response(self, data):
        return Response({
            'success': True,
            'count':    self.page.paginator.count,
            'next':     self.get_next_link(),
            'previous': self.get_previous_link(),
            'results':  data,               # ✅ frontend reads data.results
        })




@api_view(['POST'])
@authentication_classes([])
@permission_classes([])
def login_view(request):
    serializer = LoginSerializer(data=request.data)
    if not serializer.is_valid():
        return Response({'success': False, 'errors': serializer.errors},
                        status=HTTP_400_BAD_REQUEST)

    email    = serializer.validated_data['email']
    password = serializer.validated_data['password']

    user = authenticate(request, username=email, password=password)

    if user is None:
        return Response({
            'success': False,
            'message': 'Invalid email or password.'
        }, status=HTTP_400_BAD_REQUEST)

    refresh = RefreshToken.for_user(user)

    return Response({
        'success': True,
        'data': {
            'user_id':    user.id,
            'email':      user.email,
            'first_name': user.first_name,
            'last_name':  user.last_name,
            'role':       user.role,
            'access':     str(refresh.access_token),
            'refresh':    str(refresh),
        }
    }, status=HTTP_200_OK)



@api_view(['GET'])
def studentList(request):
    search = request.query_params.get('search', None)
    transport_status = request.query_params.get('transport_status', None)
    is_active = request.query_params.get('is_active', None)

    students = StudentProfile.objects.select_related('user').all().order_by('id')

    # ── Filters ──────────────────────────────────────────
    if search:
        students = students.filter(
            Q(user__first_name__icontains=search) |
            Q(user__last_name__icontains=search)  |
            Q(user__email__icontains=search)       |
            Q(admission_number__icontains=search)
        )

    if transport_status:
        students = students.filter(transport_status=transport_status)

    if is_active is not None:
        is_active_bool = is_active.lower() == 'true'
        students = students.filter(user__is_active=is_active_bool)

    # ── Paginate ──────────────────────────────────────────
    paginator = StudentPagination()
    page = paginator.paginate_queryset(students, request)
    serializer = StudentSerializer(page, many=True)
    return paginator.get_paginated_response(serializer.data)



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
