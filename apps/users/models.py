from django.db import models
from django.contrib.auth.models import AbstractUser
from django.db.models.signals import post_save
from django.dispatch import receiver


class User(AbstractUser):
    """
    Simple user model for personal expense tracking.
    No roles, no permissions - just basic user info.
    """
    email = models.EmailField(unique=True)
    full_name = models.CharField(max_length=100)
    profile_picture = models.ImageField(upload_to='profile_pictures/', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    # Login with email instead of username
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username', 'full_name']
    
    class Meta:
        db_table = 'USER'
    
    def __str__(self):
        return self.email

class UserPreference(models.Model):
    """User settings and preferences"""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='preferences')
    currency = models.CharField(max_length=3, default='USD')
    date_format = models.CharField(max_length=20, default='MM/DD/YYYY')
    timezone = models.CharField(max_length=50, default='UTC')
    ai_suggestions_enabled = models.BooleanField(default=True)
    voice_input_enabled = models.BooleanField(default=True)
    
    class Meta:
        db_table = 'USER_PREFERENCE'
    
    def __str__(self):
        return f"{self.user.email} - Preferences"
    """User preferences and settings"""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='preferences')
    currency = models.CharField(max_length=3, default='USD')
    date_format = models.CharField(max_length=20, default='MM/DD/YYYY')
    timezone = models.CharField(max_length=50, default='UTC')
    ai_suggestions_enabled = models.BooleanField(default=True)
    voice_input_enabled = models.BooleanField(default=True)
    
    class Meta:
        db_table = 'USER_PREFERENCE'
    
    def __str__(self):
        return f"{self.user.email} - Preferences"
    
@receiver(post_save, sender=User)
def create_user_preference(sender, instance, created, **kwargs):
    if created:
        UserPreference.objects.create(user=instance)


@receiver(post_save, sender=User)
def create_default_categories(sender, instance, created, **kwargs):
    if created:
        from apps.categories.models import Category
        
        default_categories = [
            {'name': 'Food & Dining', 'icon': '🍔', 'color': '#FF6B6B'},
            {'name': 'Transportation', 'icon': '🚗', 'color': '#4ECDC4'},
            {'name': 'Shopping', 'icon': '🛍️', 'color': '#95E1D3'},
            {'name': 'Bills & Utilities', 'icon': '💡', 'color': '#F38181'},
            {'name': 'Entertainment', 'icon': '🎬', 'color': '#AA96DA'},
            {'name': 'Healthcare', 'icon': '🏥', 'color': '#FCBAD3'},
            {'name': 'Other', 'icon': '📦', 'color': '#A8D8EA'},
        ]
        
        for cat in default_categories:
            Category.objects.create(
                user=instance,
                category_name=cat['name'],
                icon=cat['icon'],
                color=cat['color'],
                is_default=True
            )