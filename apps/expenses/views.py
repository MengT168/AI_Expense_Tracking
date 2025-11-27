from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import Expense
from .forms import ExpenseForm


@login_required
def expense_list(request):
    """List all expenses"""
    expenses = Expense.objects.filter(user=request.user)
    return render(request, 'expenses/expense_list.html', {
        'expenses': expenses
    })


@login_required
def expense_create(request):
    """Create new expense"""
    if request.method == 'POST':
        form = ExpenseForm(request.POST)
        if form.is_valid():
            expense = form.save(commit=False)
            expense.user = request.user
            expense.save()
            messages.success(request, 'Expense added successfully!')
            return redirect('expenses:list')
    else:
        form = ExpenseForm()
    
    return render(request, 'expenses/expense_form.html', {
        'form': form,
        'title': 'Add Expense'
    })


@login_required
def expense_detail(request, pk):
    """View expense detail"""
    expense = get_object_or_404(Expense, pk=pk, user=request.user)
    return render(request, 'expenses/expense_detail.html', {
        'expense': expense
    })


@login_required
def expense_update(request, pk):
    """Update expense"""
    expense = get_object_or_404(Expense, pk=pk, user=request.user)
    
    if request.method == 'POST':
        form = ExpenseForm(request.POST, instance=expense)
        if form.is_valid():
            form.save()
            messages.success(request, 'Expense updated successfully!')
            return redirect('expenses:list')
    else:
        form = ExpenseForm(instance=expense)
    
    return render(request, 'expenses/expense_form.html', {
        'form': form,
        'title': 'Edit Expense'
    })


@login_required
def expense_delete(request, pk):
    """Delete expense"""
    expense = get_object_or_404(Expense, pk=pk, user=request.user)
    
    if request.method == 'POST':
        expense.delete()
        messages.success(request, 'Expense deleted successfully!')
        return redirect('expenses:list')
    
    return render(request, 'expenses/expense_confirm_delete.html', {
        'expense': expense
    })


@login_required
def receipt_upload(request):
    """Upload receipt (placeholder)"""
    return render(request, 'expenses/receipt_upload.html')


@login_required
def voice_input(request):
    """Voice input (placeholder)"""
    return render(request, 'expenses/voice_input.html')


@login_required
def text_parse(request):
    """Text parsing (placeholder)"""
    return render(request, 'expenses/text_parse.html')