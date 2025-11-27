from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from .models import Category

@login_required
def category_list(request):
    categories = Category.objects.filter(user=request.user)
    return render(request, 'categories/category_list.html', {'categories': categories})