# apps/expenses/forms.py

from django import forms
from .models import Expense, Receipt
# Assuming 'apps.categories' is installed and its models are accessible
from apps.categories.models import Category 

class ExpenseForm(forms.ModelForm):
    """Form used for manual entry and for reviewing/editing OCR data."""
    class Meta:
        model = Expense
        fields = ['category', 'amount', 'expense_date', 'merchant_name', 
                  'description', 'payment_method']
        widgets = {
            'expense_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'merchant_name': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'payment_method': forms.TextInput(attrs={'class': 'form-control'}),
            'category': forms.Select(attrs={'class': 'form-control'}),
        }
    
    def __init__(self, *args, **kwargs):
        # Pop the user out of kwargs so we can filter categories
        user = kwargs.pop('user', None) 
        super().__init__(*args, **kwargs)
        
        # Filter categories for the current user
        if user:
            self.fields['category'].queryset = Category.objects.filter(user=user)
        # Fallback to general queryset if filtering isn't strictly necessary or not possible
        elif self.instance.pk:
            self.fields['category'].queryset = Category.objects.filter(user=self.instance.user)


class ReceiptUploadForm(forms.ModelForm):
    """Form for uploading a receipt image."""
    class Meta:
        model = Receipt
        fields = ['file']
        widgets = {
            'file': forms.FileInput(attrs={'id': 'receipt_file', 'accept': 'image/*'})
        }