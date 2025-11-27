# apps/budgets/views.py
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from .models import Budget

@login_required
def budget_list(request):
    budgets = Budget.objects.filter(user=request.user)
    return render(request, 'budgets/budget_list.html', {'budgets': budgets})


@login_required
def budget_create(request):
    # valid_form_logic_goes_here
    # For now, let's just render a placeholder or redirect to list
    return render(request, 'budgets/budget_form.html')