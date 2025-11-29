from django import forms
from .models import Category

class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ['category_name', 'icon', 'color']
        widgets = {
            'category_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., Pet Expenses'}),
            'icon': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., 🐕'}),
            'color': forms.TextInput(attrs={'type': 'color', 'class': 'form-control form-control-color'}),
        }