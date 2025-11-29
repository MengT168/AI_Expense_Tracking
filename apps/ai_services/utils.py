import json
from datetime import timedelta
from django.db.models import Sum
from django.utils import timezone
from apps.expenses.models import Expense
from apps.budgets.models import Budget
from .models import AIInsight

def generate_weekly_summary(user):
    """
    SCENARIO 7: Generates the 'weekly_summary' JSON logic.
    """
    today = timezone.now().date()
    start_week = today - timedelta(days=7)
    
    # 1. Get expenses for this week
    expenses = Expense.objects.filter(user=user, expense_date__gte=start_week)
    total_spent = expenses.aggregate(Sum('amount'))['amount__sum'] or 0
    
    # 2. Category Breakdown
    cat_stats = expenses.values('category__category_name').annotate(total=Sum('amount'))
    breakdown = {item['category__category_name']: float(item['total']) for item in cat_stats}
    
    # 3. Create the JSON Data
    insight_data = {
        "total_spent": float(total_spent),
        "category_breakdown": breakdown,
        "comparison_to_last_week": {"change_percentage": 15, "trend": "increased"}, # Simplified for demo
        "prediction_next_week": float(total_spent) * 1.1
    }
    
    # 4. Save to DB
    AIInsight.objects.create(
        user=user,
        insight_type='weekly_summary',
        insight_data=json.dumps(insight_data), # Store as JSON string
        message=f"You spent ${total_spent} this week. Check your breakdown!",
        period_start=start_week,
        period_end=today
    )

def check_budget_alerts(user):
    """
    Checks active budgets and returns a list of alert messages if thresholds are met.
    """
    today = timezone.now().date()
    active_budgets = Budget.objects.filter(user=user, start_date__lte=today, end_date__gte=today)
    
    generated_alerts = [] # Store messages here
    
    for budget in active_budgets:
        spent = Expense.objects.filter(
            user=user, 
            category=budget.category,
            expense_date__gte=budget.start_date,
            expense_date__lte=budget.end_date
        ).aggregate(Sum('amount'))['amount__sum'] or 0
        
        percentage = (spent / budget.budget_limit) * 100
        
        if percentage >= budget.alert_threshold:
            message = f"⚠️ Budget Alert: You've used {int(percentage)}% of your {budget.category.category_name} budget!"
            
            # Save to DB (History)
            data = {
                "category": budget.category.category_name,
                "budget_limit": float(budget.budget_limit),
                "current_spent": float(spent),
                "percentage_used": round(float(percentage), 1)
            }
            
            # Check if we already alerted today to avoid spam (Optional logic)
            # For now, we overwrite or create new
            AIInsight.objects.create(
                user=user,
                insight_type='budget_alert',
                insight_data=json.dumps(data),
                message=message,
                period_start=budget.start_date,
                period_end=budget.end_date
            )
            
            generated_alerts.append(message)

    return generated_alerts         