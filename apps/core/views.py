# apps/core/views.py

from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required


def home(request):
    """
    Homepage / Landing page
    """
    if request.user.is_authenticated:
        return redirect('core:dashboard')
    
    return render(request, 'core/home.html')


@login_required
def dashboard(request):
    """
    User dashboard - SAFE VERSION
    Won't crash if no data exists
    """
    try:
        from apps.expenses.models import Expense
        from apps.budgets.models import Budget
        from apps.categories.models import Category
        from django.db.models import Sum, Count
        from datetime import datetime
        
        # Get current month date range
        today = datetime.now()
        first_day = today.replace(day=1)
        
        # Get user's expenses for current month
        expenses_this_month = Expense.objects.filter(
            user=request.user,
            expense_date__gte=first_day,
            expense_date__lte=today
        )
        
        # Calculate total spent this month
        total_spent = expenses_this_month.aggregate(
            total=Sum('amount')
        )['total'] or 0
        
        # Get expense count
        expense_count = expenses_this_month.count()
        
        # Get spending by category
        spending_by_category = expenses_this_month.values(
            'category__category_name',
            'category__icon',
            'category__color'
        ).annotate(
            total=Sum('amount'),
            count=Count('id')
        ).order_by('-total')[:5]
        
        # Get recent expenses (last 5)
        recent_expenses = Expense.objects.filter(
            user=request.user
        ).select_related('category').order_by('-expense_date', '-created_at')[:5]
        
        # Get active budgets
        budgets = Budget.objects.filter(
            user=request.user,
            start_date__lte=today,
            end_date__gte=today
        ).select_related('category')
        
        # Calculate budget status
        budget_status = []
        for budget in budgets:
            spent = Expense.objects.filter(
                user=request.user,
                category=budget.category,
                expense_date__gte=budget.start_date,
                expense_date__lte=budget.end_date
            ).aggregate(total=Sum('amount'))['total'] or 0
            
            percentage = (spent / budget.budget_limit * 100) if budget.budget_limit > 0 else 0
            
            budget_status.append({
                'budget': budget,
                'spent': spent,
                'remaining': budget.budget_limit - spent,
                'percentage': round(percentage, 1),
                'status': 'danger' if percentage >= 100 else 'warning' if percentage >= 80 else 'success'
            })
        
        context = {
            'total_spent': total_spent,
            'expense_count': expense_count,
            'spending_by_category': spending_by_category,
            'recent_expenses': recent_expenses,
            'budget_status': budget_status,
            'current_month': today.strftime('%B %Y'),
        }
        
    except Exception as e:
        # If something goes wrong, show simple dashboard
        print(f"Dashboard error: {e}")
        from datetime import datetime
        context = {
            'total_spent': 0,
            'expense_count': 0,
            'spending_by_category': [],
            'recent_expenses': [],
            'budget_status': [],
            'current_month': datetime.now().strftime('%B %Y'),
            'error_message': 'Dashboard is loading. Please add some expenses to see your data.'
        }
    
    return render(request, 'core/dashboard.html', context)


def about(request):
    """About page"""
    return render(request, 'core/about.html')