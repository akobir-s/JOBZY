import uuid

from dateutil.relativedelta import relativedelta
from django.contrib.auth import authenticate
from django.db.models import Avg, Count, Q, Sum
from django.db.models.functions import ExtractMonth, ExtractYear
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import RefreshToken, TokenError

from .filters import ProfessionalServiceFilter
from .models import (
    AdminLog,
    AvailabilitySlot,
    Booking,
    Message,
    Notification,
    Payment,
    ProfessionalProfile,
    ProfessionalService,
    Review,
    ServiceCategory,
    User,
)
from .serializers import (
    AdminLogSerializer,
    AvatarUpdateSerializer,
    AvailabilitySlotSerializer,
    BookingSerializer,
    LoginUserSerializer,
    MessageSerializer,
    MyProfessionalProfileSerializer,
    NotificationSerializer,
    PaymentSerializer,
    ProfessionalFilterServiceSerializer,
    ProfessionalProfileDetailSerializer,
    ProfessionalProfileSerializer,
    ProfessionalProfileWriteSerializer,
    ProfessionalServiceDetailSerializer,
    ProfessionalServiceSerializer,
    ProfessionalServiceWithOwnerSerializer,
    ReviewSerializer,
    ServiceCategorySerializer,
    UserProfileSerializer,
    UserRegisterSerializer,
)


class MyTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token['username'] = user.username
        token['is_admin'] = user.is_superuser
        token['is_professional'] = user.is_professional
        return token


# --- Authentication ---------------------------------------------------------

class RegisterUserView(APIView):
    permission_classes = [permissions.AllowAny]
    serializer_class = UserRegisterSerializer

    def post(self, request):
        serializer = UserRegisterSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({'error': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

        user = serializer.save()
        token = MyTokenObtainPairSerializer.get_token(user)
        return Response(
            {
                'user': UserRegisterSerializer(user).data,
                'refresh': str(token),
                'access': str(token.access_token),
            },
            status=status.HTTP_201_CREATED,
        )


class LoginUserView(APIView):
    permission_classes = [permissions.AllowAny]
    serializer_class = LoginUserSerializer

    def post(self, request):
        serializer = LoginUserSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({'error': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

        user = authenticate(
            username=serializer.validated_data['username'],
            password=serializer.validated_data['password'],
        )
        if not user:
            return Response({'error': 'Username or password incorrect'},
                            status=status.HTTP_401_UNAUTHORIZED)

        # Preserve the prior sign-in timestamp so the UI can show "last seen".
        if user.last_login:
            user.previous_login = user.last_login
        user.last_login = timezone.now()
        user.save(update_fields=['previous_login', 'last_login'])

        token = MyTokenObtainPairSerializer.get_token(user)
        return Response(
            {
                'user': UserRegisterSerializer(user).data,
                'refresh': str(token),
                'access': str(token.access_token),
            },
            status=status.HTTP_200_OK,
        )


class LogoutUserView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        refresh_token = request.data.get('refresh')
        if not refresh_token:
            return Response({'error': "Field 'refresh' is required."},
                            status=status.HTTP_400_BAD_REQUEST)
        try:
            RefreshToken(refresh_token).blacklist()
        except TokenError:
            return Response({'error': 'Invalid or expired token'},
                            status=status.HTTP_400_BAD_REQUEST)
        return Response({'message': 'Logged out successfully'}, status=status.HTTP_200_OK)


# --- Professional profile ---------------------------------------------------

class MyProfessionalView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = MyProfessionalProfileSerializer

    def post(self, request):
        if ProfessionalProfile.objects.filter(user=request.user).exists():
            return Response({'error': 'Profile already exists'},
                            status=status.HTTP_400_BAD_REQUEST)

        serializer = MyProfessionalProfileSerializer(data=request.data,
                                                     context={'request': request})
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def get(self, request):
        profile = ProfessionalProfile.objects.filter(user=request.user).first()
        if not profile:
            return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)
        return Response(MyProfessionalProfileSerializer(profile).data, status=status.HTTP_200_OK)

    def put(self, request):
        profile = ProfessionalProfile.objects.filter(user=request.user).first()
        if not profile:
            return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)

        serializer = MyProfessionalProfileSerializer(profile, data=request.data, partial=True,
                                                     context={'request': request})
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request):
        profile = ProfessionalProfile.objects.filter(user=request.user).first()
        if not profile:
            return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)

        profile.is_available = False
        profile.save(update_fields=['is_available'])
        request.user.is_professional = False
        request.user.save(update_fields=['is_professional'])
        return Response({'message': 'Professional deactivated (profile not deleted)'},
                        status=status.HTTP_200_OK)


class ProfessionalProfileViewSet(viewsets.ModelViewSet):
    queryset = ProfessionalProfile.objects.select_related('user').all()
    serializer_class = ProfessionalProfileWriteSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    @action(detail=True, methods=['get'])
    def services(self, request, pk=None):
        professional = self.get_object()
        services = ProfessionalService.objects.filter(professional=professional)
        return Response(ProfessionalServiceSerializer(services, many=True).data)

    @action(detail=True, methods=['get'])
    def availability(self, request, pk=None):
        professional = self.get_object()
        slots = AvailabilitySlot.objects.filter(
            professional=professional, is_booked=False, end_time__gt=timezone.now()
        )
        return Response(AvailabilitySlotSerializer(slots, many=True).data)


# --- Catalogue --------------------------------------------------------------

class ServiceCategoryViewSet(viewsets.ModelViewSet):
    queryset = ServiceCategory.objects.all()
    serializer_class = ServiceCategorySerializer

    search_fields = ['name', 'description']
    ordering_fields = ['name']
    filterset_fields = ['parent']

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [permissions.AllowAny()]
        return [permissions.IsAdminUser()]


class ProfessionalServiceViewSet(viewsets.ModelViewSet):
    """A professional's own services. Requires authentication."""

    serializer_class = ProfessionalServiceSerializer
    permission_classes = [IsAuthenticated]

    search_fields = ['title', 'description']
    filterset_fields = ['category', 'is_available', 'professional']
    ordering_fields = ['fixed_price', 'min_price', 'max_price', 'duration', 'created_at']

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return ProfessionalService.objects.none()
        return ProfessionalService.objects.filter(
            professional__user=self.request.user
        ).select_related('category', 'professional__user')

    def perform_create(self, serializer):
        professional = get_object_or_404(ProfessionalProfile, user=self.request.user)
        serializer.save(professional=professional)


class IsProfessionalOwner(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        return obj.professional.user == request.user


class AvailabilitySlotViewSet(viewsets.ModelViewSet):
    serializer_class = AvailabilitySlotSerializer
    permission_classes = [IsAuthenticated, IsProfessionalOwner]

    search_fields = ['professional__user__username']
    ordering_fields = ['start_time', 'end_time']
    filterset_fields = ['is_booked', 'professional']

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return AvailabilitySlot.objects.none()

        professional_id = self.request.query_params.get('professional')
        if professional_id:
            return AvailabilitySlot.objects.filter(professional_id=professional_id)
        return AvailabilitySlot.objects.filter(professional__user=self.request.user)

    def perform_create(self, serializer):
        professional = get_object_or_404(ProfessionalProfile, user=self.request.user)
        serializer.save(professional=professional)


# --- Bookings ---------------------------------------------------------------

class BookingViewSet(viewsets.ModelViewSet):
    serializer_class = BookingSerializer
    permission_classes = [IsAuthenticated]

    ordering_fields = ['start_time', 'end_time', 'created_at', 'status']
    search_fields = ['professional__user__username', 'service__title', 'status']
    filterset_fields = ['status', 'service', 'slot']

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return Booking.objects.none()

        user = self.request.user
        return Booking.objects.filter(
            Q(client=user) | Q(professional__user=user)
        ).select_related('client', 'professional__user', 'service', 'slot').distinct()

    def perform_create(self, serializer):
        booking = serializer.save(client=self.request.user)
        if booking.slot and not booking.slot.is_booked:
            booking.slot.is_booked = True
            booking.slot.save(update_fields=['is_booked'])

    @action(detail=True, methods=['post'])
    def complete(self, request, pk=None):
        booking = self.get_object()
        if booking.professional.user != request.user:
            return Response({'error': 'Not allowed'}, status=status.HTTP_403_FORBIDDEN)
        if booking.status == 'COMPLETED':
            return Response({'error': 'Booking is already completed.'},
                            status=status.HTTP_400_BAD_REQUEST)
        if booking.status == 'CANCELLED':
            return Response({'error': 'Cannot complete a cancelled booking.'},
                            status=status.HTTP_400_BAD_REQUEST)

        booking.status = 'COMPLETED'
        booking.save(update_fields=['status', 'updated_at'])

        Notification.objects.create(
            user=booking.client,
            message=f"Your booking for '{booking.service.title}' was marked as completed.",
            link=f'/bookings/{booking.id}/',
        )
        return Response({'status': 'completed', 'booking_id': booking.id})

    @action(detail=True, methods=['post'])
    def confirm(self, request, pk=None):
        booking = self.get_object()
        if booking.professional.user != request.user:
            return Response({'error': 'Not allowed'}, status=status.HTTP_403_FORBIDDEN)
        if booking.status != 'PENDING':
            return Response({'error': 'Only pending bookings can be confirmed.'},
                            status=status.HTTP_400_BAD_REQUEST)

        booking.status = 'CONFIRMED'
        booking.save(update_fields=['status', 'updated_at'])

        Notification.objects.create(
            user=booking.client,
            message=f"Your booking for '{booking.service.title}' was confirmed.",
            link=f'/bookings/{booking.id}/',
        )
        return Response({'status': 'confirmed', 'booking_id': booking.id})

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        booking = self.get_object()
        user = request.user

        if user != booking.client and user != booking.professional.user:
            return Response({'error': 'Not allowed'}, status=status.HTTP_403_FORBIDDEN)
        if booking.status in ('COMPLETED', 'CANCELLED'):
            return Response({'error': 'Booking already completed or cancelled.'},
                            status=status.HTTP_400_BAD_REQUEST)

        reason = str(request.data.get('cancellation_reason', '')).strip()
        booking.status = 'CANCELLED'
        booking.cancellation_reason = reason or None
        booking.save(update_fields=['status', 'cancellation_reason', 'updated_at'])

        # Free the slot back up so it can be rebooked.
        if booking.slot and booking.slot.is_booked:
            booking.slot.is_booked = False
            booking.slot.save(update_fields=['is_booked'])

        suffix = f' with reason: {reason}' if reason else ''
        if user == booking.client:
            recipient = booking.professional.user
            message = (f"{booking.client.username} cancelled the booking for "
                       f"'{booking.service.title}'{suffix}.")
        else:
            recipient = booking.client
            message = (f"Your booking for '{booking.service.title}' was cancelled "
                       f'by the professional{suffix}.')

        Notification.objects.create(user=recipient, message=message,
                                    link=f'/bookings/{booking.id}/')

        return Response({
            'status': 'cancelled',
            'booking_id': booking.id,
            'cancellation_reason': reason or None,
        })


# --- Payments ---------------------------------------------------------------

class PaymentViewSet(viewsets.ModelViewSet):
    serializer_class = PaymentSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return Payment.objects.none()

        user = self.request.user
        return Payment.objects.filter(
            Q(booking__client=user) | Q(booking__professional__user=user)
        ).select_related('booking__client', 'booking__professional__user',
                         'booking__service').distinct()

    def perform_create(self, serializer):
        booking = serializer.validated_data['booking']
        if booking.client != self.request.user:
            raise PermissionDenied('You can only pay for your own bookings.')

        serializer.save(status='PENDING', transaction_id=f'TXN-{uuid.uuid4().hex[:10]}')

        Notification.objects.create(
            user=booking.professional.user,
            message=f"You have received a payment request for '{booking.service.title}'",
            link=f'/payments/{booking.id}/',
        )

    @action(detail=True, methods=['post'])
    def confirm(self, request, pk=None):
        payment = self.get_object()
        if payment.booking.professional.user != request.user:
            return Response({'error': 'Not allowed'}, status=status.HTTP_403_FORBIDDEN)
        if payment.status != 'PENDING':
            return Response({'error': 'Payment is not pending.'},
                            status=status.HTTP_400_BAD_REQUEST)

        payment.status = 'COMPLETED'
        payment.processed_at = timezone.now()
        payment.save(update_fields=['status', 'processed_at'])

        Notification.objects.create(
            user=payment.booking.client,
            message=f"Your payment for '{payment.booking.service.title}' was confirmed.",
            link=f'/payments/{payment.id}/',
        )
        return Response({'status': 'confirmed', 'payment_id': payment.id})


# --- Reviews ----------------------------------------------------------------

class ReviewViewSet(viewsets.ModelViewSet):
    serializer_class = ReviewSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return Review.objects.none()

        user = self.request.user
        return Review.objects.filter(
            Q(client=user) | Q(professional__user=user)
        ).select_related('client', 'professional__user', 'booking').distinct()

    def perform_create(self, serializer):
        booking = serializer.validated_data['booking']

        if booking.client != self.request.user:
            raise ValidationError('You can only review your own bookings.')
        if booking.status != 'COMPLETED':
            raise ValidationError('You can only review a completed booking.')
        if Review.objects.filter(booking=booking).exists():
            raise ValidationError('You have already reviewed this booking.')

        serializer.save(client=self.request.user, professional=booking.professional)


# --- Messaging & notifications ---------------------------------------------

class MessageViewSet(viewsets.ModelViewSet):
    serializer_class = MessageSerializer
    permission_classes = [IsAuthenticated]

    filterset_fields = ['booking', 'is_read', 'recipient', 'sender']
    ordering_fields = ['created_at']

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return Message.objects.none()

        user = self.request.user
        return Message.objects.filter(
            Q(sender=user) | Q(recipient=user)
        ).select_related('sender', 'recipient').distinct()

    def perform_create(self, serializer):
        serializer.save(sender=self.request.user)

    @action(detail=False, methods=['get'])
    def inbox(self, request):
        messages = Message.objects.filter(recipient=request.user).select_related('sender')
        page = self.paginate_queryset(messages)
        if page is not None:
            return self.get_paginated_response(self.get_serializer(page, many=True).data)
        return Response(self.get_serializer(messages, many=True).data)


class NotificationViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]

    filterset_fields = ['is_read']
    ordering_fields = ['created_at']

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return Notification.objects.none()
        return Notification.objects.filter(user=self.request.user)

    @action(detail=True, methods=['post'])
    def mark_as_read(self, request, pk=None):
        notification = self.get_object()
        notification.is_read = True
        notification.save(update_fields=['is_read'])
        return Response(self.get_serializer(notification).data)

    @action(detail=False, methods=['post'])
    def mark_all_as_read(self, request):
        count = Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
        return Response({'status': f'{count} notifications marked as read'})

    @action(detail=False, methods=['get'])
    def unread_count(self, request):
        count = Notification.objects.filter(user=request.user, is_read=False).count()
        return Response({'unread_count': count})


class AdminLogViewSet(viewsets.ModelViewSet):
    queryset = AdminLog.objects.select_related('admin').all()
    serializer_class = AdminLogSerializer
    permission_classes = [IsAdminUser]


# --- Public search & catalogue ---------------------------------------------

class ProfessionalSearchView(generics.ListAPIView):
    queryset = ProfessionalProfile.objects.select_related('user').all()
    serializer_class = ProfessionalProfileSerializer
    permission_classes = [permissions.AllowAny]

    search_fields = ['user__username', 'bio', 'address']
    ordering_fields = ['hourly_rate', 'years_of_experience', 'average_rating',
                       'total_completed_jobs']
    filterset_fields = ['is_available', 'average_rating', 'years_of_experience']


class ProfessionalSearchDetailView(generics.RetrieveAPIView):
    queryset = ProfessionalProfile.objects.select_related('user').all()
    serializer_class = ProfessionalProfileDetailSerializer
    permission_classes = [permissions.AllowAny]
    lookup_field = 'id'


class PublicServiceListView(generics.ListAPIView):
    queryset = ProfessionalService.objects.filter(
        is_available=True, professional__user__is_professional=True
    ).select_related('category', 'professional__user')
    serializer_class = ProfessionalFilterServiceSerializer
    permission_classes = [permissions.AllowAny]
    filterset_class = ProfessionalServiceFilter

    search_fields = ['title', 'description', 'category__name']
    ordering_fields = ['duration', 'fixed_price']


class PublicServiceDetailView(generics.RetrieveAPIView):
    queryset = ProfessionalService.objects.filter(
        is_available=True, professional__user__is_professional=True
    ).select_related('category', 'professional__user')
    serializer_class = ProfessionalServiceDetailSerializer
    permission_classes = [permissions.AllowAny]
    lookup_field = 'id'


class ProfessionalServiceDetailView(generics.RetrieveAPIView):
    """Service detail including the owning professional's contact info."""

    queryset = ProfessionalService.objects.select_related('professional__user').all()
    serializer_class = ProfessionalServiceWithOwnerSerializer
    permission_classes = [permissions.AllowAny]


# --- Current user -----------------------------------------------------------

class UserProfileView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = UserProfileSerializer

    def get(self, request):
        return Response(UserProfileSerializer(request.user).data, status=status.HTTP_200_OK)

    def put(self, request):
        serializer = UserProfileSerializer(request.user, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request):
        request.user.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class UpdateAvatarView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = AvatarUpdateSerializer

    def patch(self, request):
        serializer = AvatarUpdateSerializer(instance=request.user, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response({'avatar': serializer.data['avatar']}, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class DashboardView(APIView):
    """Lightweight per-user dashboard for the logged-in account."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        data = {'user_info': {'username': user.username, 'phone': user.phone}}

        if user.is_professional:
            professional = get_object_or_404(ProfessionalProfile, user=user)
            data['professional_stats'] = {
                'total_bookings': professional.total_completed_jobs,
                'average_rating': professional.average_rating,
            }
        return Response(data)


# --- Admin dashboard --------------------------------------------------------

class AdminDashboardView(APIView):
    """Aggregated platform statistics for the last 12 months. Staff only."""

    permission_classes = [IsAdminUser]

    def get(self, request):
        today = timezone.now()
        start_date = (today - relativedelta(months=11)).replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        )
        start_of_month = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        months = []
        cursor = start_date
        for _ in range(12):
            months.append((cursor.year, cursor.month))
            cursor += relativedelta(months=1)

        def monthly_series(queryset, date_field, value_key, aggregate):
            rows = (
                queryset.annotate(
                    year=ExtractYear(date_field), month=ExtractMonth(date_field)
                )
                .values('year', 'month')
                .annotate(value=aggregate)
                .order_by('year', 'month')
            )
            lookup = {(r['year'], r['month']): r['value'] for r in rows}
            return [
                {'month': index + 1, value_key: lookup.get((year, month), 0) or 0}
                for index, (year, month) in enumerate(months)
            ]

        # User statistics
        total_users = User.objects.count()
        professional_users = User.objects.filter(is_professional=True).count()
        monthly_registrations = monthly_series(
            User.objects.filter(created_at__gte=start_date),
            'created_at', 'count', Count('id'),
        )

        # Professional statistics
        top_rated = ProfessionalProfile.objects.select_related('user').order_by('-average_rating')[:5]
        most_jobs = ProfessionalProfile.objects.select_related('user').order_by('-total_completed_jobs')[:5]

        # Service statistics
        popular_categories = ServiceCategory.objects.annotate(
            num_services=Count('professionalservice')
        ).order_by('-num_services')[:5]
        top_rated_services = ProfessionalService.objects.annotate(
            avg_rating=Avg('booking__review__rating')
        ).filter(avg_rating__isnull=False).order_by('-avg_rating')[:5]

        # Booking statistics
        pending_bookings = Booking.objects.filter(status='PENDING').count()
        last_month_start = (start_of_month - relativedelta(days=1)).replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        )
        monthly_bookings = monthly_series(
            Booking.objects.filter(created_at__gte=start_date),
            'created_at', 'count', Count('id'),
        )

        # Payment statistics
        completed_payments = Payment.objects.filter(status='COMPLETED')
        top_earners = ProfessionalProfile.objects.select_related('user').annotate(
            total_earnings=Sum('booking__payment__amount',
                               filter=Q(booking__payment__status='COMPLETED'))
        ).exclude(total_earnings=None).order_by('-total_earnings')[:5]
        monthly_revenue = monthly_series(
            completed_payments.filter(processed_at__gte=start_date),
            'processed_at', 'amount', Sum('amount'),
        )
        for entry in monthly_revenue:
            entry['amount'] = float(entry['amount'])

        rating_distribution = Review.objects.values('rating').annotate(
            count=Count('id')
        ).order_by('rating')

        system_alerts = []
        if pending_bookings > 10:
            system_alerts.append('High number of pending bookings.')

        response_data = {
            'user_stats': {
                'total_users': total_users,
                'professional_users': professional_users,
                'regular_users': total_users - professional_users,
                'new_users_this_month': User.objects.filter(
                    created_at__gte=start_of_month).count(),
                'monthly_registrations': monthly_registrations,
            },
            'professional_stats': {
                'total_professionals': professional_users,
                'active_professionals': ProfessionalProfile.objects.filter(
                    is_available=True).count(),
                'top_rated_professionals': [
                    {'id': p.id, 'username': p.user.username,
                     'rating': float(p.average_rating or 0)}
                    for p in top_rated
                ],
                'most_completed_jobs': [
                    {'id': p.id, 'username': p.user.username,
                     'completed_jobs': p.total_completed_jobs}
                    for p in most_jobs
                ],
            },
            'service_stats': {
                'total_services': ProfessionalService.objects.count(),
                'popular_categories': [
                    {'category': c.name, 'count': c.num_services} for c in popular_categories
                ],
                'top_rated_services': [
                    {'id': s.id, 'title': s.title, 'rating': float(s.avg_rating)}
                    for s in top_rated_services
                ],
            },
            'booking_stats': {
                'total_bookings': Booking.objects.count(),
                'completed_bookings': Booking.objects.filter(status='COMPLETED').count(),
                'cancelled_bookings': Booking.objects.filter(status='CANCELLED').count(),
                'pending_bookings': pending_bookings,
                'booking_trends': {
                    'this_month': Booking.objects.filter(
                        created_at__gte=start_of_month).count(),
                    'last_month': Booking.objects.filter(
                        created_at__gte=last_month_start,
                        created_at__lt=start_of_month).count(),
                },
                'monthly_bookings': monthly_bookings,
            },
            'payment_stats': {
                'total_revenue': float(
                    completed_payments.aggregate(total=Sum('amount'))['total'] or 0),
                'average_payment': float(
                    completed_payments.aggregate(avg=Avg('amount'))['avg'] or 0),
                'payment_methods': {
                    row['payment_method']: row['count']
                    for row in Payment.objects.values('payment_method').annotate(count=Count('id'))
                },
                'top_earning_professionals': [
                    {'id': p.id, 'username': p.user.username,
                     'earnings': float(p.total_earnings or 0)}
                    for p in top_earners
                ],
                'monthly_revenue': monthly_revenue,
            },
            'review_stats': {
                'average_rating': float(
                    Review.objects.aggregate(avg=Avg('rating'))['avg'] or 0),
                'total_reviews': Review.objects.count(),
                'rating_distribution': {
                    str(r['rating']): r['count'] for r in rating_distribution
                },
            },
            'system_health': {
                'pending_bookings': pending_bookings,
                'unconfirmed_payments': Payment.objects.filter(status='PENDING').count(),
                'system_alerts': system_alerts,
            },
        }

        return Response({'data': response_data, 'statusCode': 200, 'errors': []})
