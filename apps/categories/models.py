from django.db import models
from django.conf import settings


class Category(models.Model):
    """Expense categories"""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='categories')
    category_name = models.CharField(max_length=50)
    icon = models.CharField(max_length=10, default='📦')
    color = models.CharField(max_length=7, default='#A8D8EA')
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'CATEGORY'
        verbose_name_plural = 'Categories'
        unique_together = ['user', 'category_name']
    
    def __str__(self):
        return f"{self.icon} {self.category_name}"