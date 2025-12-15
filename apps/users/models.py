import pytz
import pycountry
from django.db import models
from django.contrib.auth.models import AbstractUser
from django.db.models.signals import post_save
from django.dispatch import receiver


ALL_TIMEZONES = sorted([(tz, tz) for tz in pytz.common_timezones])

ALL_CURRENCIES = []
for currency in pycountry.currencies:
    # Some currencies don't have a name, so we handle that safely
    name = getattr(currency, 'name', currency.alpha_3)
    label = f"{currency.alpha_3} - {name}"
    ALL_CURRENCIES.append((currency.alpha_3, label))

ALL_CURRENCIES = sorted(ALL_CURRENCIES, key=lambda x: x[1])
class User(AbstractUser):
    email = models.EmailField(unique=True, max_length=191)     # Reduce from default 254
    username = models.CharField(max_length=191, unique=True)   # Reduce from default 150
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
    
    # Date Format Options (Hardcoded because they are specific to your UI)
    DATE_FORMAT_CHOICES = [
        ('YYYY-MM-DD', 'YYYY-MM-DD (2024-11-29)'),
        ('MM/DD/YYYY', 'MM/DD/YYYY (11/29/2024)'),
        ('DD/MM/YYYY', 'DD/MM/YYYY (29/11/2024)'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='preferences')
    
    # Use the Auto-Generated Lists here
    currency = models.CharField(max_length=3, choices=ALL_CURRENCIES, default='USD')
    timezone = models.CharField(max_length=50, choices=ALL_TIMEZONES, default='UTC')
    
    date_format = models.CharField(max_length=20, choices=DATE_FORMAT_CHOICES, default='YYYY-MM-DD')
    
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