# apps/expenses/ocr_service.py

import pytesseract
from PIL import Image
import datetime
from decimal import Decimal
from typing import Dict, Any
import re

# --- IMPORTANT CONFIGURATION ---
# >>> YOU MUST SET THIS PATH TO YOUR TESSERACT INSTALLATION <<<
# Example for Windows:
# pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
# ---------------------------------
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
def parse_ocr_text(raw_text: str) -> Dict[str, Any]:
    """
    Parses the raw text output from the OCR engine into structured data fields 
    using Regular Expressions, specifically targeting common receipt formats.
    """
    
    text = raw_text.upper().replace('\n', ' ').replace('$', '')
    
    # --- 1. Extract Merchant Name ---
    merchant_match = re.search(r'^([A-Z\s&]+)', text)
    merchant_name = merchant_match.group(1).strip() if merchant_match else 'Unknown Merchant (OCR)'

    # --- 2. Extract Total Amount ---
    total_match = re.search(r'(TOTAL|BALANCE|AMOUNT)\s*([\d,\.]+\.\d{2})', text)
    amount = Decimal('0.00')
    if total_match:
        try:
            amount = Decimal(total_match.group(2).replace(',', ''))
        except:
            pass 

    # --- 3. Extract Date ---
    date_match = re.search(r'DATE[:\s]*(\d{1,2}[\/-]\d{1,2}[\/-]\d{2,4})', text)
    expense_date = datetime.date.today()
    if date_match:
        date_str = date_match.group(1)
        for fmt in ('%m/%d/%Y', '%m-%d-%Y', '%d/%m/%Y', '%Y/%m/%d'):
            try:
                expense_date = datetime.datetime.strptime(date_str, fmt).date()
                break
            except ValueError:
                continue

    # --- 4. Extract Category and Payment ---
    category = 'Uncategorized'
    if 'BURGER' in merchant_name or 'CAFE' in merchant_name or 'FOOD' in text:
        category = 'Dining & Fast Food'
    elif 'SUPERMART' in merchant_name or 'GROCERY' in text:
        category = 'Food & Groceries'
        
    payment_method = 'Unknown'
    if 'VISA' in text or 'MASTERCARD' in text or 'CREDIT' in text:
        payment_method = 'Credit Card'

    # --- FINAL STRUCTURED DATA ---
    return {
        'amount': amount,
        'currency': 'USD',
        'expense_date': expense_date, 
        'merchant_name': merchant_name,
        'description': f'OCR Category: {category}. Items: {text[:150]}...',
        'payment_method': payment_method,
        'category_name': category,
    }


def perform_receipt_ocr(receipt_file_path: str) -> tuple[Dict[str, Any], str]:
    """
    Processes the receipt image using Tesseract OCR to get extracted data, 
    with a fallback to mock data on error.
    """
    print(f"Starting OCR processing for file: {receipt_file_path}")
    
    try:
        # Use pytesseract to extract text from the image file
        raw_ocr_text = pytesseract.image_to_string(Image.open(receipt_file_path))
        
        # 1. Parse the raw text into structured fields
        extracted_data = parse_ocr_text(raw_ocr_text)

        print("OCR successful.")
        
        return extracted_data, raw_ocr_text
        
    except pytesseract.TesseractNotFoundError:
        error_message = "Tesseract is not installed or not in your PATH. Falling back to mock data."
        print(f"ERROR: {error_message}")
        
        # Fallback to Mock Data if Tesseract is not found
        extracted_data = {
            'amount': Decimal('45.99'),
            'currency': 'USD',
            'expense_date': datetime.date.today(), 
            'merchant_name': 'Mock Merchant (Failed OCR)',
            'description': 'Failed to run OCR. Using mock data.',
            'payment_method': 'Mock',
            'category_name': 'Uncategorized', 
        }
        return extracted_data, error_message

    except Exception as e:
        error_message = f"OCR processing failed: {e}. Falling back to mock data."
        print(f"ERROR: {error_message}")
        
        # Fallback to Mock Data on other failure
        extracted_data = {
            'amount': Decimal('45.99'),
            'currency': 'USD',
            'expense_date': datetime.date.today(), 
            'merchant_name': 'Mock Merchant (Processing Error)',
            'description': f'Processing failed: {e}. Using mock data.',
            'payment_method': 'Mock',
            'category_name': 'Uncategorized', 
        }
        return extracted_data, error_message