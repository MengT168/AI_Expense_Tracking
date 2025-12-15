import re
import json
from datetime import timedelta
from decimal import Decimal
from apps.core.currency_rates import convert_amount

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse
from django.utils import timezone
from django.db import transaction
from apps.ai_services.utils import check_budget_alerts
from .forms import ReceiptUploadForm, ExpenseForm # <-- ENSURE ExpenseForm is importedimport numpy as np
from django.core.files.uploadedfile import UploadedFile  # <--- THIS IS THE FIX
from django.conf import settings
import os 
from .models import Expense, Receipt
from .forms import ExpenseForm
from apps.categories.models import Category
from apps.ai_services.models import AIExtraction 
from .ocr_service import perform_receipt_ocr


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
            
            alerts = check_budget_alerts(request.user)
            for alert in alerts:
                messages.warning(request, alert)

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
    """
    Update expense with Auto-Currency Conversion.
    If editing a USD expense while in KHR mode, convert the amount 
    so the user sees the correct value for their current setting.
    """
    expense = get_object_or_404(Expense, pk=pk, user=request.user)
    
    user_currency = request.user.preferences.currency if hasattr(request.user, 'preferences') else 'USD'
    
    if request.method == 'POST':
        form = ExpenseForm(request.POST, instance=expense)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.currency = user_currency 
            obj.save()
            
            messages.success(request, 'Expense updated successfully!')
            return redirect('expenses:list')
    else:

        initial_data = {}
        
        if expense.currency and expense.currency != user_currency:
            converted_amount = convert_amount(expense.amount, expense.currency, user_currency)
            
            if user_currency == 'KHR':
                initial_data['amount'] = int(converted_amount)
            else:
                initial_data['amount'] = round(converted_amount, 2)
        
        form = ExpenseForm(instance=expense, initial=initial_data)
    
    return render(request, 'expenses/expense_form.html', {
        'form': form,
        'title': 'Edit Expense'
    })

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
        
        ocr_text = """
        STARBUCKS STORE #12345
        11/25/2024 09:12 AM
        GRANDE LATTE $5.95
        CROISSANT $4.50
        TOTAL $12.45
        VISA ****1234
        """
        
        extracted = _smart_extract(ocr_text, request.user)
        amount = extracted['amount'] or Decimal('0.00')
        merchant = extracted['merchant'] if extracted['merchant'] else "Unknown Receipt"
        
        with transaction.atomic():
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
            
            Receipt.objects.create(
                expense=expense,
                file=uploaded_file,
                file_type=uploaded_file.content_type,
                ocr_text=ocr_text
            )
            
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
                messages.warning(request, alert)

        messages.success(request, "Voice command saved successfully.")
        return redirect('expenses:list')

    return render(request, 'expenses/voice_input.html')

@login_required
def text_parse(request):
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
                messages.warning(request, alert)

        messages.success(request, "Text parsed and expense saved.")
        return redirect('expenses:list')
        
    return render(request, 'expenses/text_parse.html')

@login_required 
def receipt_upload(request):
    """Handles receipt image upload, saves the Receipt, and redirects to review."""
    
    # Use the form field name 'file' from the HTML template
    if request.method == 'POST':
            form = ReceiptUploadForm(request.POST, request.FILES)
            if form.is_valid():
                receipt = form.save(commit=False)
                receipt.user = request.user
                # !!! ERROR LINE (Original) !!!
                receipt.file_type = receipt.file.content_type if receipt.file else 'unknown'
                # ... rest of the logic
                receipt.save() 
            
            # 2. Perform OCR and extract data
            receipt_file_path = os.path.join(settings.MEDIA_ROOT, receipt.file.name)
            try:
                # Use the mock OCR service
                ocr_data, raw_ocr_text = perform_receipt_ocr(receipt_file_path)
                
                # Update the receipt with the raw OCR text
                receipt.ocr_text = raw_ocr_text
                receipt.save()
                
            except Exception as e:
                messages.error(request, f"OCR processing failed for the image. Error: {e}")
                receipt.delete() # Clean up
                return redirect('expenses:receipt_upload')

            # Redirect to the review page
            return redirect('expenses:review_receipt', pk=receipt.pk)
            
    else:
            messages.error(request, "Please select a file to upload.")
            
    # GET request or failed POST
    form = ReceiptUploadForm()
    
    return render(request, 'expenses/receipt_upload.html', {'form': form})
@login_required 
def receipt_upload(request):
    """Handles receipt image upload, saves the Receipt, and redirects to review."""
    
    if request.method == 'POST':
        form = ReceiptUploadForm(request.POST, request.FILES)
        
        if form.is_valid():
            # Lines must be indented here (e.g., 4 spaces)
            uploaded_file = request.FILES.get('file') 
            
            receipt = form.save(commit=False)
            receipt.user = request.user
            
            # --- FIX APPLIED HERE (Now UploadedFile is defined) ---
            if uploaded_file and isinstance(uploaded_file, UploadedFile): 
                receipt.file_type = uploaded_file.content_type
            else:
                receipt.file_type = 'unknown' 
            # ------------------------
            
            # Save the receipt instance to store the file and other fields
            receipt.save() 
            
            # 2. Perform OCR and extract data
            # NOTE: receipt.file.name is only available after receipt.save() is called
            receipt_file_path = os.path.join(settings.MEDIA_ROOT, receipt.file.name)
            
            try:
                # Use the mock OCR service
                ocr_data, raw_ocr_text = perform_receipt_ocr(receipt_file_path)
                
                # Update the receipt with the raw OCR text
                receipt.ocr_text = raw_ocr_text
                receipt.save()
                
            except Exception as e:
                messages.error(request, f"OCR processing failed for the image. Error: {e}")
                # Clean up the object and the file saved on disk
                receipt.delete() 
                return redirect('expenses:receipt_upload')

            # Redirect to the review page
            return redirect('expenses:review_receipt', pk=receipt.pk)
        
    else:
            # If form is NOT valid (e.g., file required but missing)
            messages.error(request, "The file upload failed. Please check the form data.")
            
    # GET request or failed POST (non-valid form)
    form = ReceiptUploadForm()
    
    return render(request, 'expenses/receipt_upload.html', {'form': form})
@login_required 
def receipt_review(request, pk):
    """Allows user to review and confirm OCR-extracted data using ExpenseForm."""
    
    # Get the Receipt object that is not yet linked to an Expense
    receipt = get_object_or_404(Receipt, pk=pk, expense__isnull=True) 

    # Re-run OCR data retrieval for pre-filling the form (in a real app, you'd parse 
    # the data saved in the Receipt model, but we use the OCR service mock here for consistency)
    receipt_file_path = os.path.join(settings.MEDIA_ROOT, receipt.file.name)
    ocr_data, raw_ocr_text = perform_receipt_ocr(receipt_file_path)

    # Find the corresponding Category object based on the OCR result
    category_name_str = ocr_data.pop('category_name', 'Uncategorized')
    
    category_obj, _ = Category.objects.get_or_create(
        category_name=category_name_str, 
        
        # --- FIX APPLIED HERE: Only using the 'user' default field ---
        # The unrecognized 'notes' field has been removed to stop the FieldError.
        defaults={'user': request.user} 
    )
    
    ocr_data['category'] = category_obj 
    
    if request.method == 'POST':
        # 3. Handle POST Request (Saving the final Expense)
        form = ExpenseForm(request.POST, user=request.user) # Pass user for category filtering

        if form.is_valid():
            # Save the new Expense object
            expense = form.save(commit=False)
            
            # Set required fields that are NOT in the form
            expense.user = request.user
            expense.entry_method = 'receipt_scan'
            expense.save()
            
            # Link the new Expense object back to the existing Receipt object
            receipt.expense = expense 
            receipt.save()
            
            messages.success(request, f"Expense of ${expense.amount} confirmed and saved!")
            # Assuming you have a detail view for expenses
            return redirect('expenses:detail', pk=expense.pk) 
        else:
            messages.error(request, "Please correct the errors in the form.")
    
    else:
        # 4. Handle GET Request (Displaying the form)
        form = ExpenseForm(initial=ocr_data, user=request.user)

    context = {
        'form': form,
        'receipt': receipt,
    }
    
    return render(request, 'expenses/receipt_review.html', context)
# Placeholder for manual expense creation (fixes the current error)
@login_required 
def manual_create(request):
    """Placeholder for the manual expense creation view."""
    # In a real app, this would handle ExpenseForm and render the manual entry template.
    form = ExpenseForm(user=request.user) 
    context = {'form': form, 'entry_method': 'Manual'}
    # You would need to create a manual_create.html template
    return render(request, 'expenses/manual_create.html', context)
