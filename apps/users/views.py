from django.shortcuts import render, redirect
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse
from .forms import UserRegistrationForm, UserLoginForm, UserProfileForm, UserPreferenceForm
from .models import User, UserPreference

def register_view(request):
    """User registration view"""
    if request.user.is_authenticated:
        return redirect('core:dashboard')
    
    if request.method == 'POST':
        form = UserRegistrationForm(request.POST)
        if form.is_valid():
            # Create user
            user = form.save(commit=False)
            user.email = form.cleaned_data['email'].lower()
            user.save()
            
            # Log the user in
            login(request, user)
            
            messages.success(request, 'Welcome! Your account has been created successfully.')
            return redirect('core:dashboard')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = UserRegistrationForm()
    
    return render(request, 'users/register.html', {'form': form})


def login_view(request):
    """User login view"""
    if request.user.is_authenticated:
        return redirect('core:dashboard')
    
    if request.method == 'POST':
        form = UserLoginForm(request, data=request.POST)
        if form.is_valid():
            email = form.cleaned_data.get('username')  # It's called username but we use email
            password = form.cleaned_data.get('password')
            
            # Authenticate user
            user = authenticate(request, username=email, password=password)
            
            if user is not None:
                login(request, user)
                messages.success(request, f'Welcome back, {user.full_name}!')
                
                # Redirect to next page or dashboard
                next_url = request.GET.get('next')
                if next_url:
                    return redirect(next_url)
                return redirect('core:dashboard')
            else:
                messages.error(request, 'Invalid email or password.')
        else:
            messages.error(request, 'Invalid email or password.')
    else:
        form = UserLoginForm()
    
    return render(request, 'users/login.html', {'form': form})


def logout_view(request):
    """User logout view"""
    logout(request)
    messages.success(request, 'You have been logged out successfully.')
    return redirect('core:home')


@login_required
def profile_view(request):
    """User profile view"""
    if request.method == 'POST':
        profile_form = UserProfileForm(request.POST, request.FILES, instance=request.user)
        
        if profile_form.is_valid():
            profile_form.save()
            messages.success(request, 'Your profile has been updated!')
            return redirect('users:profile')
    else:
        profile_form = UserProfileForm(instance=request.user)
    
    return render(request, 'users/profile.html', {
        'profile_form': profile_form
    })


@login_required
def preferences_view(request):
    """User preferences view"""
    preferences, created = UserPreference.objects.get_or_create(user=request.user)
    
    if request.method == 'POST':
        form = UserPreferenceForm(request.POST, instance=preferences)
        if form.is_valid():
            form.save()
            messages.success(request, 'Your preferences have been updated!')
            return redirect('users:preferences')
    else:
        form = UserPreferenceForm(instance=preferences)
    
    return render(request, 'users/preferences.html', {'form': form})