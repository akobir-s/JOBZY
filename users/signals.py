from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from .models import ProfessionalProfile, User

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
