from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Sum
from django.utils import timezone
from .models import Budget
from .forms import BudgetForm
from apps.expenses.models import Expense

@login_required
def budget_list(request):
    """
    Shows ALL budgets (Active, Expired, and Upcoming).
    """
    today = timezone.now().date()

    budgets = Budget.objects.filter(user=request.user).order_by('-end_date')
    
    budget_data = []
    for budget in budgets:
        # 2. CALCULATE SPENDING
        spent = Expense.objects.filter(
            user=request.user,
            category=budget.category,
            expense_date__gte=budget.start_date,
            expense_date__lte=budget.end_date
        ).aggregate(total=Sum('amount'))['total'] or 0
        
        # 3. CALCULATE STATUS
        if budget.end_date < today:
            status = 'Expired'
            status_color = 'secondary'
        elif budget.start_date > today:
            status = 'Upcoming'
            status_color = 'info'
        else:
            status = 'Active'
            status_color = 'success'

        percentage = (spent / budget.budget_limit) * 100 if budget.budget_limit > 0 else 0
        remaining = budget.budget_limit - spent
        
        budget_data.append({
            'budget': budget,
            'spent': spent,
            'remaining': remaining,
            'percentage': round(percentage, 1),
            'is_alert': percentage >= budget.alert_threshold,
            'status': status,          # New field
            'status_color': status_color # New field
        })

    return render(request, 'budgets/budget_list.html', {'budget_data': budget_data})

@login_required
def budget_create(request):
    """SCENARIO 6: Create a new budget"""
    if request.method == 'POST':
        form = BudgetForm(request.user, request.POST)
        if form.is_valid():
            budget = form.save(commit=False)
            budget.user = request.user
            budget.alert_enabled = True
            budget.save()
            messages.success(request, f"Budget set for {budget.category.category_name}!")
            return redirect('budgets:list')
    else:
        form = BudgetForm(request.user)
    
    return render(request, 'budgets/budget_form.html', {'form': form})