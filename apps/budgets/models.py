from django.db import models
from django.conf import settings
from apps.categories.models import Category


class Budget(models.Model):
    """Budget limits for categories"""
    PERIOD_TYPES = [
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
        ('yearly', 'Yearly'),
    ]
    
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='budgets')
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name='budgets')
    budget_limit = models.DecimalField(max_digits=10, decimal_places=2)
    period_type = models.CharField(max_length=10, choices=PERIOD_TYPES, default='monthly')
    start_date = models.DateField()
    end_date = models.DateField()
    alert_enabled = models.BooleanField(default=True)
    alert_threshold = models.IntegerField(default=80)  # Percentage
    
    class Meta:
        db_table = 'BUDGET'
        unique_together = ['user', 'category', 'start_date', 'end_date']
    
    def __str__(self):
        return f"{self.user.email} - {self.category.category_name} - ${self.budget_limit}"
