from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from .models import ProfessionalProfile, User, Review, Booking, Notification
from django.db.models import Avg, Count

@receiver(post_save, sender=ProfessionalProfile)
def make_user_professional(sender, instance, created, **kwargs):
    if created:
        user = instance.user
        user.is_professional = True
        user.save()

@receiver(post_delete, sender=ProfessionalProfile)
def remove_user_professional(sender, instance, **kwargs):
    user = instance.user
    user.is_professional = False
    user.save()



@receiver(post_save, sender=Review)
def update_professional_profile_stats(sender, instance, created, **kwargs):
    if created:
        professional = instance.professional

        reviews = Review.objects.filter(professional=professional)
        avg_rating = reviews.aggregate(Avg('rating'))['rating__avg'] or 0.0
        total_reviews = reviews.count()

        profile = professional
        profile.average_rating = round(avg_rating, 2)
        profile.total_reviews = total_reviews
        profile.total_completed_jobs += 1  
        profile.save()



@receiver(post_save, sender=Booking)
def send_booking_notification(sender, instance, created, **kwargs):
    if created:
        Notification.objects.create(
            user=instance.professional.user,
            message=f"You have a new booking from {instance.client.username} for '{instance.service.title}'",
            link=f"/bookings/{instance.id}/"
        )        