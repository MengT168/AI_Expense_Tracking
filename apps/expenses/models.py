from django.db import models
from django.conf import settings
from apps.categories.models import Category


class Expense(models.Model):
    """Expense transactions"""
    ENTRY_METHODS = [
        ('manual', 'Manual Entry'),
        ('receipt_scan', 'Receipt Scan'),
        ('voice_input', 'Voice Input'),
        ('text_parsing', 'Text Parsing'),
    ]
    
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='expenses')
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name='expenses')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default='USD')
    expense_date = models.DateField()
    merchant_name = models.CharField(max_length=100, blank=True)
    description = models.TextField(blank=True)
    payment_method = models.CharField(max_length=50, blank=True)
    entry_method = models.CharField(max_length=20, choices=ENTRY_METHODS, default='manual')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'EXPENSE'
        ordering = ['-expense_date', '-created_at']
        indexes = [
            models.Index(fields=['user', 'expense_date']),
            models.Index(fields=['category']),
        ]
    
    def __str__(self):
        return f"{self.merchant_name} - ${self.amount}"


class Receipt(models.Model):
    """Receipt attachments for expenses"""
    # One-to-One link to the Expense created from the receipt. Null=True allows Receipt to exist 
    # temporarily before the final Expense is created/confirmed via the review page.
    expense = models.OneToOneField(
            'Expense', 
            on_delete=models.CASCADE, 
            related_name='receipt_scan', 
            null=True,           # <--- ADD THIS
            blank=True           # <--- AND THIS
        )    
    file = models.ImageField(upload_to='receipts/%Y/%m/')
    file_type = models.CharField(max_length=50, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    ocr_text = models.TextField(blank=True, null=True) # Raw text result from OCR
    
    class Meta:
        db_table = 'RECEIPT'
    
    def __str__(self):
        return f"Receipt ID {self.pk} - Linked to Expense {self.expense_id or 'Unlinked'}"