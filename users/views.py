from django.shortcuts import render
from rest_framework.views import APIView
from .serializers import *
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.response import Response
from django.contrib.auth import authenticate
from .models import *
from rest_framework import status, viewsets, permissions, generics, filters
from django.shortcuts import get_object_or_404
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from rest_framework.permissions import IsAdminUser
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import action
from django.utils import timezone
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from .filters import ProfessionalServiceFilter


class MyTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)

        token['username'] = user.username
        token['is_admin'] = user.is_superuser
        token['is_professional'] = user.is_professional

        return token



class RegisterUserView(APIView):
    def post(self, request):
        serializer = UserRegisterSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()

            token = MyTokenObtainPairSerializer.get_token(user)
            refresh_token = str(token)
            access_token = str(token.access_token)
            user_data = UserRegisterSerializer(user).data

            return Response({
                    'user': user_data,
                    'refresh': refresh_token,
                    'access': access_token
                }, status=status.HTTP_200_OK)


        return Response({'error': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)



class LoginUserView(APIView):
    def post(self, request):
        serializer = LoginUserSerilalizer(data=request.data)
        if serializer.is_valid():
            username = serializer.validated_data.get('username')
            password = serializer.validated_data.get('password')
            user = authenticate(username=username, password=password)
            if user:
                if user.last_login:
                    user.previous_login = user.last_login
                    user.last_login = timezone.now()
                    user.save()
                else:
                    user.last_login = timezone.now()
                    user.save()       
                token = MyTokenObtainPairSerializer.get_token(user)
                refresh_token = str(token)
                access_token = str(token.access_token)
                user_data = UserRegisterSerializer(user).data

                return Response({
                    'user': user_data,
                    'refresh': refresh_token,
                    'access': access_token
                }, status=status.HTTP_200_OK)

            return Response({'error': 'Username or password incorrect'},
                            status=status.HTTP_401_UNAUTHORIZED)

        return Response({'error': serializer.errors},
                        status=status.HTTP_400_BAD_REQUEST)




class LogoutUserView(APIView):

    def post(self, request):
        try:
            refresh_token = request.data.get('refresh')
            token = RefreshToken(refresh_token)
            token.blacklist()
            return Response({'message': 'Logged out successfully'},
                            status=status.HTTP_205_RESET_CONTENT)
        except Exception as e:
            return Response({'error': 'Invalid or expired token'},
                            status=status.HTTP_400_BAD_REQUEST)



class MyProfessionalView(APIView):

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = MyProfessionalProfileSerializer(data=request.data, context={'request': request})

        if ProfessionalProfile.objects.filter(user=request.user).exists():
            return Response({'error': 'Profile already exists'}, status=400)
        
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    def get(self, request):
        profile = ProfessionalProfile.objects.filter(user = request.user).first()
        if profile:
            serializer = MyProfessionalProfileSerializer(profile)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response({'error': 'NOT FOUND'} , status=status.HTTP_404_NOT_FOUND)
    

    def put(self, request):
        profile = ProfessionalProfile.objects.filter(user = request.user).first()
        if not profile:
            return Response({'error': 'Not Found '}, status=status.HTTP_404_NOT_FOUND)
        serializer = MyProfessionalProfileSerializer(profile, data = request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    def delete(self, request):
        profile = ProfessionalProfile.objects.filter(user=request.user).first()
        if not profile:
            return Response({'error': 'Not Found'}, status=status.HTTP_404_NOT_FOUND)
        
        request.user.is_professional = False
        request.user.save()
        
        return Response({'message': 'Professional deactivated (profile not deleted)'})



    
# smth
class ProfessionalProfileViewSet(viewsets.ModelViewSet):
    queryset = ProfessionalProfile.objects.all()
    serializer_class = ProfessionalProfileSerializer2
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    @action(detail=True, methods=['get'])
    def services(self, request, pk=None):
        professional = self.get_object()
        services = ProfessionalService.objects.filter(professional=professional)
        serializer = ProfessionalServiceSerializer(services, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def availability(self, request, pk=None):
        professional = self.get_object()
        slots = AvailabilitySlot.objects.filter(professional=professional,
                                                is_booked=False, end_time__gt=timezone.now())
        serializer = AvailabilitySlotSerializer(slots, many=True)
        return Response(serializer.data)



class ServiceCategoryViewSet(viewsets.ModelViewSet):
    queryset = ServiceCategory.objects.all()
    serializer_class = ServiceCategorySerializer

    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    search_fields = ['name', 'description']
    ordering_fields = ['name']
    filterset_fields = ['parent']

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [permissions.AllowAny()]
        return [permissions.IsAdminUser()]


    




class ProfessionalServiceViewSet(viewsets.ModelViewSet):
    serializer_class = ProfessionalServiceSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]

    search_fields = ['title', 'description']
    filterset_fields = ['category', 'is_available', 'professional']
    ordering_fields = ['fixed_price', 'min_price', 'max_price',
                       'duration', 'created_at']



    def get_queryset(self):
        return ProfessionalService.objects.filter(professional__user=self.request.user)

    def perform_create(self, serializer):
        professional = get_object_or_404(ProfessionalProfile, user=self.request.user)
        serializer.save(professional=professional)


class AvailabilitySlotViewSet(viewsets.ModelViewSet):
    serializer_class = AvailabilitySlotSerializer
    permission_classes = [permissions.IsAuthenticated]

    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    search_fields = ['professional__user__username']
    ordering_fields = ['start_time', 'end_time']
    filterset_fields = ['is_booked', 'professional']


    def get_queryset(self):
        return AvailabilitySlot.objects.filter(professional__user=self.request.user)

    def perform_create(self, serializer):
        professional = get_object_or_404(ProfessionalProfile, user=self.request.user)
        serializer.save(professional=professional)


class BookingViewSet(viewsets.ModelViewSet):
    serializer_class = BookingSerializer
    permission_classes = [permissions.IsAuthenticated]

    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]

    ordering_fields = ['start_time', 'end_time', 'created_at', 'status']
    search_fields = ['professional__user__username', 'service__title', 'status']
    filterset_fields = ['status', 'service', 'slot']


    def get_queryset(self):
        return Booking.objects.filter(client=self.request.user)

    def perform_create(self, serializer):
        serializer.save(client=self.request.user)

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        booking = self.get_object()
        booking.status = 'CANCELLED'
        booking.save()
        return Response({'status': 'cancelled', 'booking_id': booking.id})

    @action(detail=True, methods=['post'])
    def complete(self, request, pk=None):
        booking = self.get_object()
        booking.status = 'COMPLETED'
        booking.save()
        return Response({'status': 'completed', 'booking_id': booking.id})


class PaymentViewSet(viewsets.ModelViewSet):
    serializer_class = PaymentSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Payment.objects.filter(booking__client=self.request.user)



class ReviewViewSet(viewsets.ModelViewSet):
    serializer_class = ReviewSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Review.objects.filter(client=self.request.user)

    def perform_create(self, serializer):
        professional = serializer.validated_data.get('professional')

        has_booking = Booking.objects.filter(
            client=self.request.user,
            professional=professional,
            status='completed'  
        ).exists()

        if not has_booking:
            raise ValidationError("You can only review professionals you've booked.")

        serializer.save(client=self.request.user)



class MessageViewSet(viewsets.ModelViewSet):
    serializer_class = MessageSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Message.objects.filter(sender=self.request.user)

    def perform_create(self, serializer):
        serializer.save(sender=self.request.user)


class NotificationViewSet(viewsets.ModelViewSet):
    serializer_class = NotificationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Notification.objects.filter(user=self.request.user)


class AdminLogViewSet(viewsets.ModelViewSet):
    queryset = AdminLog.objects.all()
    serializer_class = AdminLogSerializer
    permission_classes = [permissions.IsAdminUser]


class ProfessionalSearchView(generics.ListAPIView):
    serializer_class = ProfessionalProfileSerializer
    permission_classes = [permissions.AllowAny]

    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]

    search_fields = ['user__username', 'bio', 'address',]
    ordering_fields = ['hourly_rate', 'years_of_experience',
                       'average_rating', 'total_completed_jobs']
    filterset_fields = ['is_available', 'average_rating', 'years_of_experience']



    def get_queryset(self):
        return ProfessionalProfile.objects.all()


class DashboardView(generics.RetrieveAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def retrieve(self, request, *args, **kwargs):
        user = request.user
        data = {
            'user_info': {
                'username': user.username,
                'phone': user.phone
            }
        }
        if user.is_professional:
            professional = get_object_or_404(ProfessionalProfile, user=user)
            data['professional_stats'] = {
                'total_bookings': professional.total_completed_jobs,
                'average_rating': professional.average_rating
            }
        return Response(data)





class PublicServiceListView(generics.ListAPIView):
    queryset = ProfessionalService.objects.filter(
        is_available=True,
        professional__user__is_professional=True
    )
    serializer_class = ProfessionalFilterServiceSerializer
    filterset_class = ProfessionalServiceFilter
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]

    search_fields = ['title', 'description', 'category__name']
    ordering_fields = ['duration', 'fixed_price']



# get user

class UserProfileView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = UserProfileSerializer(request.user)
        if serializer:
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response({'error': "Not found"}, status=status.HTTP_404_NOT_FOUND)
    
    def put(self, request):
        serializer = UserProfileSerializer(request.user, data=request.data,
                                           partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


    def delete(self, request):
        user = request.user
        user.delete()
        return Response({'detail': 'User deleted successfully.'},
                        status=status.HTTP_204_NO_CONTENT)
    


# request for new  ServiceCategory

class ProfessionalServiceDetailView(generics.RetrieveAPIView):
    queryset = ProfessionalService.objects.all()
    serializer_class = ProfessionalServiceSerializer2


# AVATAR

class UpdateAvatarView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request):
        serializer = AvatarUpdateSerializer(instance=request.user, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response({'avatar': serializer.data['avatar']}, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

