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
from django.db.models import Count, Sum, Avg, Q
import uuid
from rest_framework.exceptions import PermissionDenied
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from django.db.models.functions import ExtractYear, ExtractMonth

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


class IsProfessionalOwner(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        # Allow read-only for all authenticated users
        if request.method in permissions.SAFE_METHODS:
            return True
        # Only the professional who owns the slot can modify it
        return obj.professional.user == request.user



class AvailabilitySlotViewSet(viewsets.ModelViewSet):
    serializer_class = AvailabilitySlotSerializer
    permission_classes = [permissions.IsAuthenticated, IsProfessionalOwner]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    search_fields = ['professional__user__username']
    ordering_fields = ['start_time', 'end_time']
    filterset_fields = ['is_booked', 'professional']

    def get_queryset(self):
        professional_id = self.request.query_params.get('professional')
        if professional_id:
            # Allow filtering by professional ID for authenticated users
            return AvailabilitySlot.objects.filter(professional_id=professional_id)
        # Default to slots owned by the authenticated professional
        return AvailabilitySlot.objects.filter(professional__user=self.request.user)

    def perform_create(self, serializer):
        # Ensure only professionals can create slots for themselves
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
        user = self.request.user
        return Booking.objects.filter(
            Q(client=user) | Q(professional__user=user)
        ).distinct()

    def perform_create(self, serializer):
        serializer.save(client=self.request.user)

    @action(detail=True, methods=['post'])
    def complete(self, request, pk=None):
        booking = self.get_object()
        if booking.professional.user != request.user:
            return Response({'error': 'Not allowed'}, status=403)
        booking.status = 'COMPLETED'
        booking.save()
        return Response({'status': 'completed', 'booking_id': booking.id})
    


    @action(detail=True, methods=['post'])
    def confirm(self, request, pk=None):
        booking = self.get_object()
        if booking.professional.user != request.user:
            return Response({'error': 'Not allowed'}, status=403)
        booking.status = 'CONFIRMED'
        booking.save()

        # notification 
        Notification.objects.create(
            user=booking.client,
            message=f"Your booking for '{booking.service.title}' was confirmed!",
            link=f"/bookings/{booking.id}/"
        )

        return Response({'status': 'confirmed', 'booking_id': booking.id})


    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        booking = self.get_object()
        user = request.user

        if user != booking.client and user != booking.professional.user:
            return Response({'error': 'Not allowed'}, status=403)

        if booking.status in ['COMPLETED', 'CANCELLED']:
            return Response({'error': 'Booking already completed or cancelled.'}, status=400)

        cancellation_reason = request.data.get('cancellation_reason', '').strip()
        if cancellation_reason:
            booking.cancellation_reason = cancellation_reason

        booking.status = 'CANCELLED'
        booking.save()

        if user == booking.client:
            if cancellation_reason:
                message = f"{booking.client.username} has cancelled the booking for '{booking.service.title}' with reason: {cancellation_reason}."
            else:
                message = f"{booking.client.username} has cancelled the booking for '{booking.service.title}'."
            recipient = booking.professional.user
        else:
            if cancellation_reason:
                message = f"Your booking for '{booking.service.title}' was cancelled by the professional with reason: {cancellation_reason}."
            else:
                message = f"Your booking for '{booking.service.title}' was cancelled by the professional."
            recipient = booking.client

        Notification.objects.create(
            user=recipient,
            message=message,
            link=f"/bookings/{booking.id}/"
        )

        return Response({
            'status': 'cancelled',
            'booking_id': booking.id,
            'cancellation_reason': cancellation_reason or None
        })






class PaymentViewSet(viewsets.ModelViewSet):
    serializer_class = PaymentSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        return Payment.objects.filter(
            Q(booking__client=user) | Q(booking__professional__user=user)
        ).distinct()

    def perform_create(self, serializer):
        booking = serializer.validated_data['booking']
        if booking.client != self.request.user:
            raise PermissionDenied("You can only pay for your own bookings.")

        serializer.save(
            status='PENDING',
            transaction_id=f"TXN-{uuid.uuid4().hex[:10]}",
        )

        Notification.objects.create(
            user=booking.professional.user,
            message=f"You have received a payment request for '{booking.service.title}'",
            link=f"/payments/{booking.id}/"
        )

    @action(detail=True, methods=['post'])
    def confirm(self, request, pk=None):
        payment = self.get_object()

        if payment.booking.professional.user != request.user:
            return Response({'error': 'Not allowed'}, status=403)

        if payment.status != 'PENDING':
            return Response({'error': 'Payment is not pending.'}, status=400)

        payment.status = 'COMPLETED'
        payment.processed_at = timezone.now()
        payment.save()

        Notification.objects.create(
            user=payment.booking.client,
            message=f"Your payment for '{payment.booking.service.title}' was confirmed.",
            link=f"/payments/{payment.id}/"
        )

        return Response({'status': 'confirmed', 'payment_id': payment.id})



class ReviewViewSet(viewsets.ModelViewSet):
    serializer_class = ReviewSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Review.objects.filter(client=self.request.user)

    def perform_create(self, serializer):
        booking = serializer.validated_data.get('booking')

        if booking.client != self.request.user:
            raise ValidationError("You can only review your own bookings.")

        if Review.objects.filter(booking=booking).exists():
            raise ValidationError("You have already reviewed this booking.")

        serializer.save(
            client=self.request.user,
            professional=booking.professional
        )



class MessageViewSet(viewsets.ModelViewSet):
    serializer_class = MessageSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Message.objects.filter(sender=self.request.user)

    def perform_create(self, serializer):
        serializer.save(sender=self.request.user)



class NotificationViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = NotificationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Notification.objects.filter(user=self.request.user)

    @action(detail=True, methods=['post'])
    def mark_as_read(self, request, pk=None):
        """
        Mark a single notification as read.
        """
        notification = self.get_object()
        notification.is_read = True
        notification.save()
        serializer = self.get_serializer(notification)
        return Response(serializer.data)

    @action(detail=False, methods=['post'])
    def mark_all_as_read(self, request):
        """
        Mark all unread notifications for the user as read.
        """
        notifications = Notification.objects.filter(user=request.user, is_read=False)
        count = notifications.count()
        notifications.update(is_read=True)
        return Response({'status': f'{count} notifications marked as read'})



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
    

class ProfessionalSearchDetailView(generics.RetrieveAPIView):
    queryset = ProfessionalProfile.objects.all() 
    serializer_class = ProfessionalProfileDetailSerializer
    permission_classes = [permissions.AllowAny]
    lookup_field = 'id'



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


class PublicServiceDetailView(generics.RetrieveAPIView):
    queryset = ProfessionalService.objects.filter(
        is_available=True,
        professional__user__is_professional=True
    )
    serializer_class = ProfessionalServiceDetailSerializer
    lookup_field = 'id'


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




class AdminDashboardView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        # Calculate the start date for the last 12 months
        today = timezone.now()
        start_date = (today - relativedelta(months=11)).replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        # Generate list of (year, month) tuples for the last 12 months
        months = []
        current_date = start_date
        for _ in range(12):
            months.append((current_date.year, current_date.month))
            current_date += relativedelta(months=1)

        ### User Statistics
        total_users = User.objects.count()
        professional_users = User.objects.filter(is_professional=True).count()
        regular_users = total_users - professional_users
        start_of_month = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        new_users_this_month = User.objects.filter(created_at__gte=start_of_month).count()

        # Monthly User Registrations
        user_counts = User.objects.filter(created_at__gte=start_date).annotate(
            year=ExtractYear('created_at'),
            month=ExtractMonth('created_at')
        ).values('year', 'month').annotate(count=Count('id')).order_by('year', 'month')
        user_count_dict = {(uc['year'], uc['month']): uc['count'] for uc in user_counts}
        monthly_registrations = [
            {"month": i + 1, "count": user_count_dict.get((year, month), 0)}
            for i, (year, month) in enumerate(months)
        ]

        ### Professional Statistics
        total_professionals = professional_users
        active_professionals = ProfessionalProfile.objects.filter(is_available=True).count()
        top_rated_professionals = ProfessionalProfile.objects.order_by('-average_rating')[:5]
        most_completed_jobs = ProfessionalProfile.objects.order_by('-total_completed_jobs')[:5]

        ### Service Statistics
        total_services = ProfessionalService.objects.count()
        popular_categories = ServiceCategory.objects.annotate(
            num_services=Count('professionalservice')
        ).order_by('-num_services')[:5]
        services_with_ratings = ProfessionalService.objects.annotate(
            avg_rating=Avg('booking__review__rating')
        ).filter(avg_rating__isnull=False).order_by('-avg_rating')[:5]

        ### Booking Statistics
        total_bookings = Booking.objects.count()
        completed_bookings = Booking.objects.filter(status='COMPLETED').count()
        cancelled_bookings = Booking.objects.filter(status='CANCELLED').count()
        pending_bookings = Booking.objects.filter(status='PENDING').count()
        this_month_bookings = Booking.objects.filter(created_at__gte=start_of_month).count()
        last_month_end = start_of_month - relativedelta(days=1)
        last_month_start = last_month_end.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        last_month_bookings = Booking.objects.filter(
            created_at__gte=last_month_start,
            created_at__lt=start_of_month
        ).count()

        # Monthly Bookings
        booking_counts = Booking.objects.filter(created_at__gte=start_date).annotate(
            year=ExtractYear('created_at'),
            month=ExtractMonth('created_at')
        ).values('year', 'month').annotate(count=Count('id')).order_by('year', 'month')
        booking_count_dict = {(bc['year'], bc['month']): bc['count'] for bc in booking_counts}
        monthly_bookings = [
            {"month": i + 1, "count": booking_count_dict.get((year, month), 0)}
            for i, (year, month) in enumerate(months)
        ]

        ### Payment Statistics
        total_revenue = Payment.objects.filter(status='COMPLETED').aggregate(total=Sum('amount'))['total'] or 0
        average_payment = Payment.objects.filter(status='COMPLETED').aggregate(avg=Avg('amount'))['avg'] or 0
        payment_methods = Payment.objects.values('payment_method').annotate(count=Count('id'))
        top_earning_professionals = ProfessionalProfile.objects.annotate(
            total_earnings=Sum('booking__payment__amount', filter=Q(booking__payment__status='COMPLETED'))
        ).order_by('-total_earnings')[:5]

        # Monthly Revenue
        revenue_data = Payment.objects.filter(status='COMPLETED', processed_at__gte=start_date).annotate(
            year=ExtractYear('processed_at'),
            month=ExtractMonth('processed_at')
        ).values('year', 'month').annotate(total=Sum('amount')).order_by('year', 'month')
        revenue_dict = {(rd['year'], rd['month']): rd['total'] for rd in revenue_data}
        monthly_revenue = [
            {"month": i + 1, "amount": float(revenue_dict.get((year, month), 0.0))}
            for i, (year, month) in enumerate(months)
        ]

        ### Review Statistics
        average_rating = Review.objects.aggregate(avg=Avg('rating'))['avg'] or 0
        total_reviews = Review.objects.count()
        rating_distribution = Review.objects.values('rating').annotate(count=Count('id')).order_by('rating')

        ### System Health
        unconfirmed_payments = Payment.objects.filter(status='PENDING').count()
        system_alerts = []
        if pending_bookings > 10:
            system_alerts.append("High number of pending bookings.")

        ### Build the Response Data
        response_data = {
            "user_stats": {
                "total_users": total_users,
                "professional_users": professional_users,
                "regular_users": regular_users,
                "new_users_this_month": new_users_this_month,
                "monthly_registrations": monthly_registrations
            },
            "professional_stats": {
                "total_professionals": total_professionals,
                "active_professionals": active_professionals,
                "top_rated_professionals": [
                    {"id": p.id, "username": p.user.username, "rating": float(p.average_rating or 0)}
                    for p in top_rated_professionals
                ],
                "most_completed_jobs": [
                    {"id": p.id, "username": p.user.username, "completed_jobs": p.total_completed_jobs}
                    for p in most_completed_jobs
                ]
            },
            "service_stats": {
                "total_services": total_services,
                "popular_categories": [
                    {"category": c.name, "count": c.num_services}
                    for c in popular_categories
                ],
                "top_rated_services": [
                    {"id": s.id, "title": s.title, "rating": float(s.avg_rating)}
                    for s in services_with_ratings
                ]
            },
            "booking_stats": {
                "total_bookings": total_bookings,
                "completed_bookings": completed_bookings,
                "cancelled_bookings": cancelled_bookings,
                "pending_bookings": pending_bookings,
                "booking_trends": {
                    "this_month": this_month_bookings,
                    "last_month": last_month_bookings
                },
                "monthly_bookings": monthly_bookings
            },
            "payment_stats": {
                "total_revenue": float(total_revenue),
                "average_payment": float(average_payment),
                "payment_methods": {pm['payment_method']: pm['count'] for pm in payment_methods},
                "top_earning_professionals": [
                    {"id": p.id, "username": p.user.username, "earnings": float(p.total_earnings or 0)}
                    for p in top_earning_professionals
                ],
                "monthly_revenue": monthly_revenue
            },
            "review_stats": {
                "average_rating": float(average_rating),
                "total_reviews": total_reviews,
                "rating_distribution": {str(r['rating']): r['count'] for r in rating_distribution}
            },
            "system_health": {
                "pending_bookings": pending_bookings,
                "unconfirmed_payments": unconfirmed_payments,
                "system_alerts": system_alerts
            }
        }

        # Return the Response
        return Response({
            "data": response_data,
            "statusCode": 200,
            "errors": []
        })