from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import AIInsight
from .utils import generate_weekly_summary, check_budget_alerts

@login_required
def insight_list(request):
    """View generated insights"""
    insights = AIInsight.objects.filter(user=request.user).order_by('-generated_at')
    
    # Convert JSON string back to Dict for the template
    # (Or use a template filter, but this is explicit)
    import json
    for item in insights:
        if isinstance(item.insight_data, str):
            item.insight_data_dict = json.loads(item.insight_data)
        else:
             item.insight_data_dict = item.insight_data

    return render(request, 'ai_services/insight_list.html', {'insights': insights})

@login_required
def trigger_analysis(request):
    """Button click to manually run AI analysis"""
    generate_weekly_summary(request.user)
    check_budget_alerts(request.user)
    messages.success(request, "AI Analysis complete! New insights generated.")
    return redirect('ai_services:list')