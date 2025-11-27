# from django.dispatch import receiver
# from django.db.models.signals import post_save 
# from django.contrib.auth.models import User

# @receiver(post_save, sender=User)
# def create_user_preference(sender, instance, created, **kwargs):
#     """Automatically create preferences when user registers"""
#     if created:
#         UserPreference.objects.create(user=instance)


# @receiver(post_save, sender=User)
# def create_default_categories(sender, instance, created, **kwargs):
#     """Automatically create default categories when user registers"""
#     if created:
#         from apps.categories.models import Category
        
#         default_categories = [
#             {'name': 'Food & Dining', 'icon': '🍔', 'color': '#FF6B6B'},
#             {'name': 'Transportation', 'icon': '🚗', 'color': '#4ECDC4'},
#             {'name': 'Shopping', 'icon': '🛍️', 'color': '#95E1D3'},
#             {'name': 'Bills & Utilities', 'icon': '💡', 'color': '#F38181'},
#             {'name': 'Entertainment', 'icon': '🎬', 'color': '#AA96DA'},
#             {'name': 'Healthcare', 'icon': '🏥', 'color': '#FCBAD3'},
#             {'name': 'Other', 'icon': '📦', 'color': '#A8D8EA'},
#         ]
        
#         for cat in default_categories:
#             Category.objects.create(
#                 user=instance,
#                 category_name=cat['name'],
#                 icon=cat['icon'],
#                 color=cat['color'],
#                 is_default=True
#             )