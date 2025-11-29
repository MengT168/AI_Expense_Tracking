import re
import json
from datetime import timedelta
from decimal import Decimal

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse
from django.utils import timezone
from django.db import transaction
from apps.ai_services.utils import check_budget_alerts

from .models import Expense, Receipt
from .forms import ExpenseForm
from apps.categories.models import Category
from apps.ai_services.models import AIExtraction 


def _smart_extract(text, user):
    """
    Simulates the AI Brain (NLP). 
    Extracts: Amount, Date (relative), Merchant, Category, Payment Method.
    """
    text_lower = text.lower()
    today = timezone.now().date()
    
    data = {
        'amount': None,
        'date': today,
        'merchant': '',
        'category': None,
        'payment_method': 'Cash',
        'confidence': 0.0
    }

    # 1. EXTRACT AMOUNT (Regex for currency)
    amount_match = re.search(r'(?:\$|USD\s?)?(\d+\.\d{2}|\d+)', text)
    if amount_match:
        data['amount'] = Decimal(amount_match.group(1))
        data['confidence'] += 0.3

    # 2. EXTRACT DATE (Relative NLP)
    if 'yesterday' in text_lower:
        data['date'] = today - timedelta(days=1)
        data['confidence'] += 0.2
    elif 'today' in text_lower:
        data['date'] = today

    # 3. EXTRACT PAYMENT METHOD
    if any(x in text_lower for x in ['card', 'visa', 'amex', 'credit']):
        data['payment_method'] = 'Credit Card'
        data['confidence'] += 0.2
    elif 'transfer' in text_lower:
        data['payment_method'] = 'Bank Transfer'

    # 4. EXTRACT CATEGORY (Keyword Matching)
    keywords = {
        'Food & Dining': ['food', 'lunch', 'dinner', 'burger', 'pizza', 'coffee'],
        'Transportation': ['uber', 'taxi', 'gas', 'fuel', 'bus'],
        'Shopping': ['walmart', 'amazon', 'groceries', 'clothes', 'shoes'],
        'Bills & Utilities': ['bill', 'electric', 'water', 'internet', 'rent'],
    }
    
    for cat_name, tags in keywords.items():
        if any(tag in text_lower for tag in tags):
            category = Category.objects.filter(user=user, category_name=cat_name).first()
            if category:
                data['category'] = category
                data['confidence'] += 0.2
                break
    
    # 5. EXTRACT MERCHANT (Simple Heuristic)
    known_merchants = ['Starbucks', 'Walmart', 'Uber', 'Olive Garden', 'Burger Kingdom', 'Electric Company']
    for m in known_merchants:
        if m.lower() in text_lower:
            data['merchant'] = m
            break
            
    return data


@login_required
def expense_list(request):
    expenses = Expense.objects.filter(user=request.user)
    return render(request, 'expenses/expense_list.html', {'expenses': expenses})

@login_required
def expense_create(request):
    """
    Create new expense (Manual Entry)
    """
    if request.method == 'POST':
        form = ExpenseForm(request.POST)
        if form.is_valid():
            # 1. Save the Expense first
            expense = form.save(commit=False)
            expense.user = request.user
            expense.save()
            
            # 2. Check for Budget Alerts (Now that expense is saved)
            alerts = check_budget_alerts(request.user)
            for alert in alerts:
                # 'warning' tag triggers the Red Popup in base.html
                messages.warning(request, alert)

            # 3. Success Message
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
    expense = get_object_or_404(Expense, pk=pk, user=request.user)
    return render(request, 'expenses/expense_detail.html', {'expense': expense})

@login_required
def expense_update(request, pk):
    expense = get_object_or_404(Expense, pk=pk, user=request.user)
    if request.method == 'POST':
        form = ExpenseForm(request.POST, instance=expense)
        if form.is_valid():
            form.save()
            messages.success(request, 'Expense updated successfully!')
            return redirect('expenses:list')
    else:
        form = ExpenseForm(instance=expense)
    return render(request, 'expenses/expense_form.html', {'form': form, 'title': 'Edit Expense'})

@login_required
def expense_delete(request, pk):
    expense = get_object_or_404(Expense, pk=pk, user=request.user)
    if request.method == 'POST':
        expense.delete()
        messages.success(request, 'Expense deleted successfully!')
        return redirect('expenses:list')
    return render(request, 'expenses/expense_confirm_delete.html', {'expense': expense})


@login_required
def receipt_upload(request):
    """SCENARIO 3: Receipt -> OCR -> Insert Expense + Receipt + AI Log"""
    if request.method == 'POST' and request.FILES.get('receipt_file'):
        uploaded_file = request.FILES['receipt_file']
        
        # 1. SIMULATE OCR (Simulating the Starbucks Receipt)
        ocr_text = """
        STARBUCKS STORE #12345
        11/25/2024 09:12 AM
        GRANDE LATTE $5.95
        CROISSANT $4.50
        TOTAL $12.45
        VISA ****1234
        """
        
        # 2. PROCESS DATA
        extracted = _smart_extract(ocr_text, request.user)
        amount = extracted['amount'] or Decimal('0.00')
        merchant = extracted['merchant'] if extracted['merchant'] else "Unknown Receipt"
        
        with transaction.atomic():
            # A. Create Expense
            expense = Expense.objects.create(
                user=request.user,
                category=extracted['category'],
                amount=amount,
                expense_date=extracted['date'],
                merchant_name=merchant,
                description="Receipt Scan: Auto-processed",
                payment_method=extracted['payment_method'],
                entry_method='receipt_scan'
            )
            
            # B. Create Receipt (Using the model in expenses)
            Receipt.objects.create(
                expense=expense,
                file=uploaded_file,
                file_type=uploaded_file.content_type,
                ocr_text=ocr_text
            )
            
            # C. Create AI Extraction (Using the model in ai_services)
            ai_log_data = {
                "detected_text": ocr_text.strip()[:50],
                "extracted_fields": {"merchant": merchant, "amount": float(amount)}
            }
            AIExtraction.objects.create(
                expense=expense,
                raw_data=ai_log_data,
                confidence_score=extracted['confidence'],
                extraction_method='ocr_vision_api'
            )

        messages.success(request, f"Receipt processed! Saved expense for {merchant}.")
        return redirect('expenses:list')

    return render(request, 'expenses/receipt_upload.html')

@login_required
def voice_input(request):
    """SCENARIO 4: Voice -> NLP -> Insert Expense + AI Log"""
    if request.method == 'POST':
        voice_text = request.POST.get('voice_text', '')
        extracted = _smart_extract(voice_text, request.user)
        
        with transaction.atomic():
            expense = Expense.objects.create(
                user=request.user,
                category=extracted['category'],
                amount=extracted['amount'] or 0.00,
                expense_date=extracted['date'],
                merchant_name=extracted['merchant'] or "Voice Entry",
                description=f"Voice: {voice_text}",
                payment_method=extracted['payment_method'],
                entry_method='voice_input'
            )
            
            ai_log_data = {"voice_transcript": voice_text}
            AIExtraction.objects.create(
                expense=expense,
                raw_data=ai_log_data,
                confidence_score=extracted['confidence'],
                extraction_method='nlp_voice_processing'
            )

            alerts = check_budget_alerts(request.user)
            for alert in alerts:
                # Add as a 'warning' message so it stands out
                messages.warning(request, alert)

        messages.success(request, "Voice command saved successfully.")
        return redirect('expenses:list')

    return render(request, 'expenses/voice_input.html')

@login_required
def text_parse(request):
    """SCENARIO 5: Text -> NLP -> Insert Expense + AI Log"""
    if request.method == 'POST':
        raw_text = request.POST.get('raw_text', '')
        extracted = _smart_extract(raw_text, request.user)
        
        with transaction.atomic():
            expense = Expense.objects.create(
                user=request.user,
                category=extracted['category'],
                amount=extracted['amount'] or 0.00,
                expense_date=extracted['date'],
                merchant_name=extracted['merchant'] or "Quick Add",
                description=f"Quick Add: {raw_text}",
                payment_method=extracted['payment_method'],
                entry_method='text_parsing'
            )
            
            ai_log_data = {"user_input": raw_text}
            AIExtraction.objects.create(
                expense=expense,
                raw_data=ai_log_data,
                confidence_score=extracted['confidence'],
                extraction_method='nlp_text_parsing'
            )

            alerts = check_budget_alerts(request.user)
            for alert in alerts:
                # Add as a 'warning' message so it stands out
                messages.warning(request, alert)

        messages.success(request, "Text parsed and expense saved.")
        return redirect('expenses:list')
        
    return render(request, 'expenses/text_parse.html')