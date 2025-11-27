from django import forms
from .models import Expense
from apps.categories.models import Category


class ExpenseForm(forms.ModelForm):
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
        super().__init__(*args, **kwargs)
        # Filter categories for current user if instance exists
        if 'instance' in kwargs and kwargs['instance'].pk:
            self.fields['category'].queryset = Category.objects.filter(
                user=kwargs['instance'].user
            )
