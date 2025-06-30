from rest_framework import serializers
from .models import *
from django.contrib.auth import get_user_model, hashers
from rest_framework.exceptions import ValidationError
from datetime import timezone
User = get_user_model()

class UserRegisterSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['username',
            'password',
            'first_name',
            'last_name',
            'phone',
            'avatar']
        extra_kwargs = {'password': {'write_only': True}}

    
    def create(self, validated_data):
        password = validated_data.pop('password')
        user = User(**validated_data)
        user.set_password(password)  
        user.save()
        return user
    

class LoginUserSerilalizer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField()



class UserProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields  = ('id', 'username', 'phone', 'first_name', 'last_name', 'avatar',
                   'is_professional', 'is_verified', 'created_at' )
        read_only = ('id', 'created_at', 'is_verified')

class MyProfessionalProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProfessionalProfile
        fields = "__all__"
        read_only_fields = ('user', 'average_rating', 'total_reviews',
                     'total_completed_jobs')
        
    def create(self, validated_data):
        validated_data['user'] = self.context['request'].user 
        return super().create(validated_data)


class ProfessionalProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProfessionalProfile
        fields = '__all__'
        read_only_fields = ('user', 'average_rating', 'total_reviews',
                     'total_completed_jobs')
        

class ProfessionalProfileSerializer2(serializers.ModelSerializer):
    class Meta:
        model = ProfessionalProfile
        fields = '__all__'
        read_only_fields = ('average_rating', 'total_reviews',
                     'total_completed_jobs')        

    def create(self, validated_data):
        user = self.context['request'].user
        if ProfessionalProfile.objects.filter(user=user).exists():
            raise ValidationError("User already has a professional profile.")
        validated_data['user'] = user
        return super().create(validated_data)




class ServiceCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ServiceCategory
        fields = '__all__'


class ProfessionalServiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProfessionalService
        fields = '__all__'
        read_only_fields = ['professional']


class AvailabilitySlotSerializer(serializers.ModelSerializer):
    class Meta:
        model = AvailabilitySlot
        fields = '__all__'
        read_only_fields = ['professional']


class BookingSerializer(serializers.ModelSerializer):
    class Meta:
        model = Booking
        fields = '__all__'
        read_only_fields = ['client']


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = '__all__'


class ReviewSerializer(serializers.ModelSerializer):
    class Meta:
        model = Review
        fields = '__all__'
        read_only_fields = ['client']


class MessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Message
        fields = '__all__'
        read_only_fields = ['sender']


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = '__all__'
        read_only_fields = ['user']


class AdminLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = AdminLog
        fields = '__all__'


class ProfessionalProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProfessionalProfile
        fields = '__all__'
        read_only_fields = ['user', 'average_rating', 'total_reviews', 'total_completed_jobs']




class ProfessionalFilterServiceSerializer(serializers.ModelSerializer):
    category = serializers.SlugRelatedField(read_only=True, slug_field='name')

    class Meta:
        model = ProfessionalService
        fields = '__all__'