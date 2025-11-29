from django import forms
from .models import Budget
from apps.categories.models import Category

class BudgetForm(forms.ModelForm):
    class Meta:
        model = Budget
        fields = ['category', 'budget_limit', 'period_type', 'start_date', 'end_date', 'alert_threshold']
        widgets = {
            'category': forms.Select(attrs={'class': 'form-control'}),
            'budget_limit': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'period_type': forms.Select(attrs={'class': 'form-control'}),
            'start_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'end_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'alert_threshold': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'e.g., 80'}),
        }

    def __init__(self, user, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Only show categories belonging to this user
        self.fields['category'].queryset = Category.objects.filter(user=user)