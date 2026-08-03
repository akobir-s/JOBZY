from django.db.models import Avg, Count
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import Booking, Notification, ProfessionalProfile, Review


@receiver(post_save, sender=ProfessionalProfile)
def make_user_professional(sender, instance, created, **kwargs):
    if created and not instance.user.is_professional:
        instance.user.is_professional = True
        instance.user.save(update_fields=['is_professional'])


@receiver(post_delete, sender=ProfessionalProfile)
def remove_user_professional(sender, instance, **kwargs):
    user = instance.user
    if user.is_professional:
        user.is_professional = False
        user.save(update_fields=['is_professional'])


def _recalculate_rating(profile):
    """Recompute rating aggregates from the reviews themselves.

    Recomputing rather than incrementing keeps the numbers correct when a
    review is edited or deleted.
    """
    stats = Review.objects.filter(professional=profile).aggregate(
        average=Avg('rating'), total=Count('id')
    )
    profile.average_rating = round(stats['average'] or 0.0, 2)
    profile.total_reviews = stats['total'] or 0
    profile.save(update_fields=['average_rating', 'total_reviews'])


@receiver(post_save, sender=Review)
def update_professional_rating(sender, instance, **kwargs):
    _recalculate_rating(instance.professional)


@receiver(post_delete, sender=Review)
def recalculate_rating_on_review_delete(sender, instance, **kwargs):
    _recalculate_rating(instance.professional)


@receiver(post_save, sender=Booking)
def handle_booking_saved(sender, instance, created, **kwargs):
    if created:
        Notification.objects.create(
            user=instance.professional.user,
            message=(f'You have a new booking from {instance.client.username} '
                     f"for '{instance.service.title}'"),
            link=f'/bookings/{instance.id}/',
        )
        return

    # The completed-job counter is derived from bookings, not from reviews.
    if instance.status == 'COMPLETED':
        profile = instance.professional
        completed = Booking.objects.filter(professional=profile, status='COMPLETED').count()
        if profile.total_completed_jobs != completed:
            profile.total_completed_jobs = completed
            profile.save(update_fields=['total_completed_jobs'])
