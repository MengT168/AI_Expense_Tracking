from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from .models import User, UserPreference

class UserRegistrationForm(UserCreationForm):
    """Form for user registration"""
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'Email address'
        })
    )
    full_name = forms.CharField(
        max_length=100,
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Full name'
        })
    )
    password1 = forms.CharField(
        label='Password',
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Password'
        })
    )
    password2 = forms.CharField(
        label='Confirm Password',
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Confirm password'
        })
    )
    
    class Meta:
        model = User
        fields = ['email', 'full_name', 'username', 'password1', 'password2']
        widgets = {
            'username': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Username'
            })
        }
    
    def clean_email(self):
        email = self.cleaned_data.get('email')
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError('This email is already registered.')
        return email


class UserLoginForm(AuthenticationForm):
    """Form for user login"""
    username = forms.EmailField(
        label='Email',
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'Email address',
            'autofocus': True
        })
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Password'
        })
    )


class UserProfileForm(forms.ModelForm):
    """Form for editing user profile"""
    class Meta:
        model = User
        fields = ['full_name', 'email', 'profile_picture']
        widgets = {
            'full_name': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'profile_picture': forms.FileInput(attrs={'class': 'form-control'}),
        }


class UserPreferenceForm(forms.ModelForm):
    """Form for editing user preferences"""
    class Meta:
        model = UserPreference
        fields = ['currency', 'date_format', 'timezone', 'ai_suggestions_enabled', 'voice_input_enabled']
        widgets = {
            # 'form-select' makes the dropdown look good in Bootstrap 5
            'currency': forms.Select(attrs={'class': 'form-select'}),
            'date_format': forms.Select(attrs={'class': 'form-select'}),
            'timezone': forms.Select(attrs={'class': 'form-select'}),
            
            # 'form-check-input' makes the checkboxes look like switches
            'ai_suggestions_enabled': forms.CheckboxInput(attrs={'class': 'form-check-input', 'role': 'switch'}),
            'voice_input_enabled': forms.CheckboxInput(attrs={'class': 'form-check-input', 'role': 'switch'}),
        }