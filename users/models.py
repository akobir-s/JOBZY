from django.db import models
from django.contrib.auth.models import AbstractUser
from django.core.validators import MinValueValidator, MaxValueValidator
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType


class User(AbstractUser):
    username = models.CharField(max_length=32, null=False, unique=True)
    password = models.CharField(max_length=128)
    first_name = models.CharField(max_length=30)
    last_name = models.CharField(max_length=30)
    phone = models.CharField(max_length=20, unique=True)
    avatar = models.ImageField(upload_to='avatars/', null=True, blank=True)
    is_professional = models.BooleanField(default=False)
    is_verified = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_login = models.DateTimeField(null=True)
    previous_login = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.username


class ProfessionalProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    bio = models.TextField()
    hourly_rate = models.DecimalField(max_digits=10, decimal_places=2)
    years_of_experience = models.IntegerField()
    is_available = models.BooleanField(default=True)
    address = models.CharField(max_length=255)
    license_number = models.CharField(max_length=100, blank=True)
    average_rating = models.FloatField(default=0.0)
    total_reviews = models.IntegerField(default=0)
    total_completed_jobs = models.IntegerField(default=0)

    def __str__(self):
        return f"{self.user.username} - {self.address}"


class ServiceCategory(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)
    icon = models.CharField(max_length=50)
    parent = models.ForeignKey('self', null=True, on_delete=models.SET_NULL)
    description = models.TextField(blank=True)

    def __str__(self):
        return self.name


class ProfessionalService(models.Model):
    professional = models.ForeignKey(ProfessionalProfile, on_delete=models.CASCADE)
    category = models.ForeignKey(ServiceCategory, on_delete=models.PROTECT)
    title = models.CharField(max_length=200)
    description = models.TextField()
    fixed_price = models.DecimalField(max_digits=10, decimal_places=2, null=True)
    min_price = models.DecimalField(max_digits=10, decimal_places=2, null=True)
    max_price = models.DecimalField(max_digits=10, decimal_places=2, null=True)
    duration = models.IntegerField()
    is_available = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    image = models.ImageField(upload_to='service_images/', null=True, blank=True)

    def __str__(self):
        return f"{self.title} - {self.professional.user.username}"


class AvailabilitySlot(models.Model):
    professional = models.ForeignKey(ProfessionalProfile, on_delete=models.CASCADE)
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    recurrence_rule = models.CharField(max_length=100, blank=True)
    is_booked = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.professional.user.username} ({self.start_time} - {self.end_time})"


class Booking(models.Model):
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('CONFIRMED', 'Confirmed'),
        ('COMPLETED', 'Completed'),
        ('CANCELLED', 'Cancelled'),
        ('NO_SHOW', 'No Show')
    ]
    client = models.ForeignKey(User, on_delete=models.CASCADE)
    professional = models.ForeignKey(ProfessionalProfile, on_delete=models.CASCADE)
    service = models.ForeignKey(ProfessionalService, on_delete=models.PROTECT)
    slot = models.ForeignKey(AvailabilitySlot, on_delete=models.PROTECT, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    start_time = models.DateTimeField(null=True, blank=True)
    end_time = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    cancellation_reason = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"Booking by {self.client.username} for {self.service.title}"


class Payment(models.Model):
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('COMPLETED', 'Completed'),
        ('FAILED', 'Failed'),
        ('REFUNDED', 'Refunded')
    ]
    PAYMENT_METHOD_CHOICES = [
        ('CARD', 'Card'),
        ('CASH', 'Cash'),
        ('OTHER', 'Other'),
    ]

    booking = models.OneToOneField(Booking, on_delete=models.PROTECT)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    transaction_id = models.CharField(max_length=100)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True)

    def __str__(self):
        return f"{self.booking.client.username} - {self.amount} ({self.status})"


class Review(models.Model):
    booking = models.OneToOneField(Booking, on_delete=models.CASCADE, related_name='review')
    professional = models.ForeignKey(ProfessionalProfile, on_delete=models.CASCADE, related_name='reviews')
    client = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='client_reviews')
    rating = models.IntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    comment = models.TextField()
    response = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Review by {self.client.username if self.client else 'Unknown'} - {self.rating} stars"


class Message(models.Model):
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_messages')
    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='received_messages')
    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, null=True)
    content = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"From {self.sender.username} to {self.recipient.username}"


class Notification(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    message = models.CharField(max_length=255)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    link = models.URLField(null=True)

    def __str__(self):
        return f"Notification for {self.user.username}"


class AdminLog(models.Model):
    ACTION_CHOICES = [
        ('USER_VERIFICATION', 'User Verification'),
        ('CONTENT_REVIEW', 'Content Review'),
        ('DISPUTE_RESOLUTION', 'Dispute Resolution')
    ]
    admin = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    action_type = models.CharField(max_length=50, choices=ACTION_CHOICES)
    target_id = models.IntegerField()
    details = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.action_type} by {self.admin.username if self.admin else 'Unknown'}"