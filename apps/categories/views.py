from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import Category
from .forms import CategoryForm

@login_required
def category_list(request):
    """List user's categories"""
    categories = Category.objects.filter(user=request.user)
    return render(request, 'categories/category_list.html', {'categories': categories})

@login_required
def category_create(request):
    """SCENARIO 8: User Creates Custom Category"""
    if request.method == 'POST':
        form = CategoryForm(request.POST)
        if form.is_valid():
            category = form.save(commit=False)
            category.user = request.user
            category.is_default = False  # Custom category
            category.save()
            messages.success(request, f"Category '{category.category_name}' created!")
            return redirect('categories:list')
    else:
        form = CategoryForm()
    
    return render(request, 'categories/category_form.html', {'form': form})