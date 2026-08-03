from django.contrib.auth import get_user_model
from django.utils.text import slugify
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from unidecode import unidecode

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
)

User = get_user_model()


# --- Users & auth -----------------------------------------------------------

class UserRegisterSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'password', 'first_name', 'last_name', 'phone', 'avatar']
        extra_kwargs = {
            'password': {'write_only': True, 'min_length': 8},
            'id': {'read_only': True},
        }

    def create(self, validated_data):
        password = validated_data.pop('password')
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user


class LoginUserSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True)


class UserProfileSerializer(serializers.ModelSerializer):
    previous_login = serializers.DateTimeField(format='%d-%m-%Y %H:%M:%S', read_only=True)

    class Meta:
        model = User
        fields = [
            'id', 'username', 'first_name', 'last_name', 'phone', 'avatar',
            'is_professional', 'is_verified', 'created_at', 'previous_login',
        ]
        read_only_fields = ['id', 'created_at', 'is_verified', 'is_professional', 'previous_login']


class UserShortInfoSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'phone', 'avatar']


class UserMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'phone', 'avatar']


class AvatarUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['avatar']


# --- Professional profiles --------------------------------------------------

class MyProfessionalProfileSerializer(serializers.ModelSerializer):
    """Used by the /my-profile/ endpoint; the owner is taken from the request."""

    class Meta:
        model = ProfessionalProfile
        fields = '__all__'
        read_only_fields = ['user', 'average_rating', 'total_reviews', 'total_completed_jobs']

    def create(self, validated_data):
        validated_data['user'] = self.context['request'].user
        return super().create(validated_data)


class ProfessionalProfileSerializer(serializers.ModelSerializer):
    """Read-oriented representation used by search/list endpoints."""

    user = serializers.SerializerMethodField()

    class Meta:
        model = ProfessionalProfile
        fields = [
            'id', 'user', 'bio', 'hourly_rate', 'years_of_experience',
            'is_available', 'address', 'average_rating', 'total_reviews',
            'total_completed_jobs',
        ]
        read_only_fields = ['user', 'average_rating', 'total_reviews', 'total_completed_jobs']

    def get_user(self, obj):
        return {
            'id': obj.user.id,
            'username': obj.user.username,
            'avatar': obj.user.avatar.url if obj.user.avatar else None,
        }


class ProfessionalProfileDetailSerializer(serializers.ModelSerializer):
    """Full public detail view of a single professional."""

    user = serializers.SerializerMethodField()

    class Meta:
        model = ProfessionalProfile
        fields = [
            'id', 'user', 'bio', 'hourly_rate', 'years_of_experience',
            'is_available', 'address', 'average_rating', 'total_reviews',
            'total_completed_jobs',
        ]
        read_only_fields = ['user', 'average_rating', 'total_reviews', 'total_completed_jobs']

    def get_user(self, obj):
        return {
            'id': obj.user.id,
            'username': obj.user.username,
            'phone': obj.user.phone,
            'first_name': obj.user.first_name,
            'last_name': obj.user.last_name,
            'avatar': obj.user.avatar.url if obj.user.avatar else None,
        }


class ProfessionalProfileWriteSerializer(serializers.ModelSerializer):
    """Writable profile serializer used by the /professionals/ viewset."""

    class Meta:
        model = ProfessionalProfile
        fields = '__all__'
        read_only_fields = ['user', 'average_rating', 'total_reviews', 'total_completed_jobs']

    def create(self, validated_data):
        user = self.context['request'].user
        if ProfessionalProfile.objects.filter(user=user).exists():
            raise ValidationError('User already has a professional profile.')
        validated_data['user'] = user
        return super().create(validated_data)


# --- Catalogue --------------------------------------------------------------

class ServiceCategorySerializer(serializers.ModelSerializer):
    slug = serializers.ReadOnlyField()

    class Meta:
        model = ServiceCategory
        fields = '__all__'

    def create(self, validated_data):
        slug = slugify(unidecode(validated_data['name']))
        if ServiceCategory.objects.filter(slug=slug).exists():
            raise ValidationError({'name': 'Category with similar name already exists.'})
        validated_data['slug'] = slug
        return super().create(validated_data)

    def update(self, instance, validated_data):
        if 'name' in validated_data:
            validated_data['slug'] = slugify(unidecode(validated_data['name']))
        return super().update(instance, validated_data)


class ProfessionalServiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProfessionalService
        fields = '__all__'
        read_only_fields = ['professional']


class ProfessionalServiceDetailSerializer(serializers.ModelSerializer):
    """Public service detail, including the owning professional's user info."""

    category = serializers.SlugRelatedField(read_only=True, slug_field='name')
    user = serializers.SerializerMethodField()

    class Meta:
        model = ProfessionalService
        fields = '__all__'

    def get_user(self, obj):
        return UserShortInfoSerializer(obj.professional.user).data


class ProfessionalServiceWithOwnerSerializer(serializers.ModelSerializer):
    professional_user = serializers.SerializerMethodField()

    class Meta:
        model = ProfessionalService
        fields = '__all__'

    def get_professional_user(self, obj):
        return UserMiniSerializer(obj.professional.user).data


class ProfessionalFilterServiceSerializer(serializers.ModelSerializer):
    category = serializers.SlugRelatedField(read_only=True, slug_field='name')

    class Meta:
        model = ProfessionalService
        fields = '__all__'


# --- Scheduling & transactions ---------------------------------------------

class AvailabilitySlotSerializer(serializers.ModelSerializer):
    class Meta:
        model = AvailabilitySlot
        fields = ['id', 'professional', 'start_time', 'end_time', 'recurrence_rule', 'is_booked']
        read_only_fields = ['professional', 'is_booked']

    def validate(self, attrs):
        start = attrs.get('start_time', getattr(self.instance, 'start_time', None))
        end = attrs.get('end_time', getattr(self.instance, 'end_time', None))
        if start and end and end <= start:
            raise ValidationError({'end_time': 'end_time must be after start_time.'})
        return attrs


class BookingSerializer(serializers.ModelSerializer):
    class Meta:
        model = Booking
        fields = [
            'id', 'client', 'professional', 'service', 'slot', 'status', 'notes',
            'created_at', 'updated_at', 'cancellation_reason', 'start_time', 'end_time',
        ]
        read_only_fields = ['client', 'status', 'created_at', 'updated_at', 'cancellation_reason']

    def validate(self, attrs):
        slot = attrs.get('slot')
        service = attrs.get('service')
        professional = attrs.get('professional')

        if slot and slot.is_booked:
            raise ValidationError({'slot': 'This slot is already booked.'})
        if slot and professional and slot.professional_id != professional.id:
            raise ValidationError({'slot': 'Slot does not belong to the selected professional.'})
        if service and professional and service.professional_id != professional.id:
            raise ValidationError({'service': 'Service does not belong to the selected professional.'})
        return attrs


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = '__all__'
        read_only_fields = ['status', 'transaction_id', 'created_at', 'processed_at']


class ReviewSerializer(serializers.ModelSerializer):
    class Meta:
        model = Review
        fields = '__all__'
        read_only_fields = ['client', 'professional', 'created_at', 'updated_at']


# --- Messaging & notifications ---------------------------------------------

class MessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Message
        fields = '__all__'
        read_only_fields = ['sender', 'created_at']


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = '__all__'
        read_only_fields = ['user', 'message', 'link', 'created_at']


class AdminLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = AdminLog
        fields = '__all__'
