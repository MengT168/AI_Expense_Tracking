import re
import easyocr
import numpy as np
from decimal import Decimal
from datetime import datetime, timedelta

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.db import transaction
from django.conf import settings

# Project Imports
from .models import Expense, Receipt
from .forms import ExpenseForm
from apps.categories.models import Category
from apps.ai_services.models import AIExtraction
from apps.ai_services.utils import check_budget_alerts
from apps.core.currency_rates import convert_amount

# ==========================================
#  AI BRAIN: EXTRACTION LOGIC
# ==========================================

def _clean_price_token(token):
    """
    Cleans a single token string into a Decimal.
    """
    if not token:
        return None
    
    token = token.strip()
    token = re.sub(r'[$€£¥៛]', '', token)
    
    if ',' in token and '.' in token:
        parts = token.split('.')
        if len(parts) == 2:
            parts[0] = parts[0].replace(',', '')
            token = '.'.join(parts)
    
    pattern = r'^\d+\.\d{2}$'
    if not re.match(pattern, token):
        if '.' not in token:
            token = token + '.00'
        else:
            parts = token.split('.')
            if len(parts) == 2:
                parts[1] = parts[1][:2].ljust(2, '0')
                token = '.'.join(parts)
    
    try:
        val = Decimal(token)
        if val > 50000 or val < 0.01:
            return None
        if 1000 <= val <= 9999 and float(val).is_integer():
            return None
        if 2020 <= val <= 2030:
            return None
        return val
    except:
        return None


def _extract_amounts_from_line(line):
    """
    Extract all potential amounts from a single line.
    """
    amounts = []
    line = ' '.join(line.split())
    
    print(f"    Analyzing: '{line}'")
    
    # Check if this line should be excluded
    exclusion_check = line.lower()
    if any(exc in exclusion_check for exc in ['cash', 'change', 'payment', 'tender', 'visa', 'card']):
        print(f"    🚫 Line excluded")
        return []
    
    # Pattern 1: Dollar sign + amount
    pattern1 = r'\$\s*(\d{1,6}\.\d{2})\b'
    for match in re.finditer(pattern1, line):
        amount_str = match.group(1)
        print(f"      Pattern1: ${amount_str}")
        val = _clean_price_token(amount_str)
        if val:
            amounts.append(val)
            print(f"      ✓ ${val}")
    
    # Pattern 2: Standalone amounts
    pattern2 = r'(?<![.\d])(\d{1,6}\.\d{2})(?![.\d])'
    for match in re.finditer(pattern2, line):
        amount_str = match.group(1)
        start_pos = match.start()
        
        # Skip if already captured by pattern1
        if start_pos > 0 and line[start_pos-1] == '$':
            continue
        
        print(f"      Pattern2: {amount_str}")
        val = _clean_price_token(amount_str)
        if val:
            amounts.append(val)
            print(f"      ✓ ${val}")
    
    # Remove duplicates
    seen = set()
    unique_amounts = []
    for amt in amounts:
        if amt not in seen:
            seen.add(amt)
            unique_amounts.append(amt)
    
    if unique_amounts:
        print(f"      📊 Found: {unique_amounts}")
    else:
        print(f"      ⚪ No amounts")
    
    return unique_amounts


def _smart_extract(text, user):
    """
    Advanced Extraction Algorithm for Receipt Upload.
    Smart detection with case-insensitive keyword matching.
    """
    text_lower = text.lower()
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    today = timezone.now().date()
    
    data = {
        'amount': None,
        'date': today,
        'merchant': '',
        'category': None,
        'payment_method': 'Cash',
        'notes': '',
        'confidence': 0.0
    }

    print(f"\n{'='*70}")
    print(f"EXTRACTION DEBUG - {len(lines)} lines")
    print(f"{'='*70}")

    # EXTRACT AMOUNT with enhanced keyword detection
    candidates = []
    
    # Priority keywords (case-insensitive)
    priority_keywords = [
        (['total amount', 'totalamount', 'amount total', 'tot amt'], 1000, 'TOTAL AMOUNT'),
        (['grand total', 'grandtotal'], 900, 'GRAND TOTAL'),
        (['final total', 'finaltotal', 'net total', 'nettotal'], 850, 'FINAL TOTAL'),
        (['amount due', 'amountdue', 'due amount'], 800, 'AMOUNT DUE'),
        (['balance due', 'balancedue', 'due balance'], 750, 'BALANCE DUE'),
        (['total', 'tot', 'ttl'], 600, 'TOTAL'),
        (['sub total', 'subtotal', 'sub-total', 'sub ttl'], 400, 'SUBTOTAL'),
        (['amount', 'amt'], 300, 'AMOUNT'),
        (['balance', 'bal'], 200, 'BALANCE'),
    ]
    
    # Absolute exclusions
    exclusion_keywords = [
        'cash', 'change', 'change due', 'tender', 'tendered',
        'payment', 'visa', 'card', 'mastercard', 'amex', 'credit card', 'debit card',
        'received', 'given', 'discount', 'savings', 'you saved'
    ]
    
    print("\n🔍 SMART KEYWORD SEARCH:")
    
    for i, line in enumerate(lines):
        line_clean = line.lower().strip()
        line_original = line.strip()
        
        # Super normalize: remove ALL spaces, dashes, underscores, colons for matching
        line_super_normalized = re.sub(r'[\s\-_:;.,]+', '', line_clean)
        # Also keep version with single spaces
        line_space_normalized = re.sub(r'[\s\-_:;.,]+', ' ', line_clean).strip()
        
        print(f"\n📍 Line {i}: '{line_original}'")
        print(f"   Super normalized: '{line_super_normalized}'")
        
        # Skip excluded lines
        if any(exc in line_clean for exc in exclusion_keywords):
            print(f"  🚫 EXCLUDED (contains: {[e for e in exclusion_keywords if e in line_clean]})")
            continue
        
        # Find ALL matching keywords and pick the most specific
        matching_keywords = []
        
        for keyword_variations, score, name in priority_keywords:
            keyword_matched = False
            matched_variation = ""
            
            for keyword in keyword_variations:
                # Create multiple versions of the keyword to match
                keyword_no_space = keyword.replace(' ', '').replace('-', '')
                keyword_with_space = keyword.replace('-', ' ')
                
                # Check in multiple normalized versions
                if (keyword_no_space in line_super_normalized or 
                    keyword_with_space in line_space_normalized or
                    keyword in line_clean):
                    
                    # Special handling: if line has "subtotal", don't match plain "total"
                    if keyword in ['total', 'tot', 'ttl']:
                        # Check if subtotal indicators exist
                        subtotal_no_space = ['subtotal', 'subtot', 'subttl', 'sub']
                        if any(ind in line_super_normalized for ind in subtotal_no_space):
                            # But also check if the word "sub" appears BEFORE "total"
                            # This prevents "TOTAL" line from being mistaken as subtotal
                            sub_indicators_with_space = ['sub total', 'subtotal', 'sub-total', 'sub tot']
                            if any(ind in line_space_normalized for ind in sub_indicators_with_space):
                                print(f"  ⚠️ Skipping '{keyword}' - line has SUBTOTAL indicators")
                                keyword_matched = False
                                break
                    
                    keyword_matched = True
                    matched_variation = keyword
                    print(f"  ✓ Matched: '{keyword}' → {name} (score: {score})")
                    break  # Found a match in this variation group
            
            if keyword_matched:
                matching_keywords.append((matched_variation, score, name, len(matched_variation)))
        
        if not matching_keywords:
            print(f"  ⚪ No keyword match")
            continue
        
        # Sort by: score (highest), then keyword length (longest = most specific)
        matching_keywords.sort(key=lambda x: (x[1], x[3]), reverse=True)
        keyword_text, keyword_score, keyword_name, _ = matching_keywords[0]
        
        print(f"  🎯 BEST MATCH: '{keyword_text}' → {keyword_name} (score: {keyword_score})")
        
        # Extract amounts from this line
        amounts_in_line = _extract_amounts_from_line(line_original)
        
        # If no amount on this line, check next line
        if not amounts_in_line and i + 1 < len(lines):
            next_line = lines[i + 1]
            next_line_clean = next_line.lower().strip()
            
            if not any(exc in next_line_clean for exc in exclusion_keywords):
                print(f"  📋 Checking next line: '{next_line}'")
                amounts_in_line = _extract_amounts_from_line(next_line)
                if amounts_in_line:
                    print(f"  ✨ Found amount on next line!")
        
        if not amounts_in_line:
            print(f"  ⚠️ No amount found")
            continue
        
        # Add all amounts from this line with keyword score
        for amount in amounts_in_line:
            print(f"  ✅ CANDIDATE: ${amount} with {keyword_name} (score: {keyword_score})")
            candidates.append((amount, keyword_score, i, f"{keyword_name}: {line_original}"))
    
    # Select best candidate
    if candidates:
        # Sort by score (highest first), then by line position (later = better)
        candidates.sort(key=lambda x: (x[1], x[2]), reverse=True)
        
        print(f"\n📊 ALL CANDIDATES:")
        for amt, score, line_num, desc in candidates[:5]:  # Show top 5
            print(f"   ${amt} - score {score} - {desc[:50]}")
        
        best_amount, best_score, line_idx, debug_info = candidates[0]
        data['amount'] = best_amount
        
        print(f"\n🎯 SELECTED: ${best_amount} (score: {best_score})")
        print(f"   From: {debug_info}")
        
        # Calculate confidence based on score
        if best_score >= 800:
            data['confidence'] += 0.95
        elif best_score >= 600:
            data['confidence'] += 0.90
        elif best_score >= 400:
            data['confidence'] += 0.75
        else:
            data['confidence'] += 0.60
    else:
        # Fallback strategy
        print("\n⚠️ NO KEYWORD MATCHES FOUND")
        print("🔄 Using fallback: largest reasonable amount...")
        
        all_amounts = []
        for i, line in enumerate(lines):
            line_lower = line.lower()
            # Skip obvious exclusions
            if any(exc in line_lower for exc in exclusion_keywords):
                continue
            
            amounts = _extract_amounts_from_line(line)
            for amt in amounts:
                all_amounts.append((amt, i, line))
        
        if all_amounts:
            # Filter reasonable amounts
            reasonable = [(a, i, l) for a, i, l in all_amounts if 0.50 <= a <= 5000]
            
            if reasonable:
                # Pick largest (likely the total)
                reasonable.sort(key=lambda x: x[0], reverse=True)
                fallback_amount, fallback_line_idx, fallback_line = reasonable[0]
                
                data['amount'] = fallback_amount
                data['confidence'] += 0.30
                print(f"🔄 FALLBACK: ${fallback_amount}")
                print(f"   From line {fallback_line_idx}: {fallback_line}")
            else:
                data['amount'] = Decimal('0.00')
                print("❌ NO REASONABLE AMOUNTS")
        else:
            data['amount'] = Decimal('0.00')
            print("❌ NO AMOUNTS FOUND")

    # EXTRACT DATE with comprehensive smart detection
    date_found = False
    
    # Create super-normalized version of text for keyword matching (no spaces)
    text_super_normalized = re.sub(r'[\s\-_:;.,]+', '', text.lower())
    text_space_normalized = re.sub(r'[\s\-_:;.,]+', ' ', text.lower()).strip()
    
    print(f"\n📅 DATE DETECTION:")
    
    # Priority date keywords with variations (case-insensitive, spacing-agnostic)
    date_keyword_groups = [
        ['duedate', 'due date', 'due-date'],
        ['transactiondate', 'transaction date', 'trans date', 'transdate'],
        ['purchasedate', 'purchase date'],
        ['receiptdate', 'receipt date'],
        ['saledate', 'sale date'],
        ['orderdate', 'order date'],
        ['invoicedate', 'invoice date'],
        ['date', 'dated'],
    ]
    
    # Comprehensive date patterns (ordered by specificity)
    date_patterns = [
        # 1. Text month formats (28 August 2022, August 28 2022, 28-Aug-2022)
        (r'(\d{1,2})\s*(?:st|nd|rd|th)?\s*[,\s\-]*\s*(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)[,\s\-]+(\d{4})', 
         lambda m: f"{m.group(1)} {m.group(2)} {m.group(3)}", 
         ['%d %B %Y', '%d %b %Y'],
         'text_month_day_first'),
        
        (r'(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})',
         lambda m: f"{m.group(2)} {m.group(1)} {m.group(3)}",
         ['%d %B %Y', '%d %b %Y'],
         'text_month_month_first'),
        
        # 2. ISO format (2024-12-21, 2024/12/21, 20241221)
        (r'(\d{4})[/-](\d{1,2})[/-](\d{1,2})',
         lambda m: f"{m.group(1)}-{m.group(2)}-{m.group(3)}",
         ['%Y-%m-%d', '%Y/%m/%d'],
         'iso_format'),
        
        (r'\b(20\d{2})(\d{2})(\d{2})\b',
         lambda m: f"{m.group(1)}-{m.group(2)}-{m.group(3)}",
         ['%Y-%m-%d'],
         'compact_format'),
        
        # 3. Standard formats (12/05/2024, 12-05-2024, 28 12 2025)
        (r'\b(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})\b',
         lambda m: f"{m.group(1)}/{m.group(2)}/{m.group(3)}",
         ['%m/%d/%Y', '%d/%m/%Y'],
         'standard_4digit_year'),
        
        (r'\b(\d{1,2})\s+(\d{1,2})\s+(\d{4})\b',
         lambda m: f"{m.group(1)}/{m.group(2)}/{m.group(3)}",
         ['%m/%d/%Y', '%d/%m/%Y'],
         'space_separated'),
        
        # 4. Short year formats (12/05/24, 12-05-24)
        (r'\b(\d{1,2})[/\-](\d{1,2})[/\-](\d{2})\b',
         lambda m: f"{m.group(1)}/{m.group(2)}/{m.group(3)}",
         ['%m/%d/%y', '%d/%m/%y'],
         'short_year'),
    ]
    
    # First, try to find dates near keywords
    for keyword_group in date_keyword_groups:
        for keyword in keyword_group:
            keyword_no_space = keyword.replace(' ', '').replace('-', '')
            keyword_with_space = keyword.replace('-', ' ')
            
            # Check if keyword exists in text
            keyword_found = False
            keyword_position = -1
            
            if keyword_no_space in text_super_normalized:
                keyword_found = True
                keyword_position = text_super_normalized.find(keyword_no_space)
                print(f"   🔑 Found keyword: '{keyword}' (no space version)")
            elif keyword_with_space in text_space_normalized:
                keyword_found = True
                keyword_position = text_space_normalized.find(keyword_with_space)
                print(f"   🔑 Found keyword: '{keyword}' (with space version)")
            
            if keyword_found:
                # Look for date patterns near this keyword (within 50 chars)
                start_pos = max(0, keyword_position - 10)
                end_pos = min(len(text), keyword_position + 100)
                nearby_text = text[start_pos:end_pos]
                
                print(f"   📝 Searching near keyword: '{nearby_text[:60]}...'")
                
                for pattern, extractor, formats, pattern_name in date_patterns:
                    match = re.search(pattern, nearby_text, re.IGNORECASE)
                    if match:
                        try:
                            date_str = extractor(match)
                            print(f"   ✓ Pattern matched ({pattern_name}): {match.group(0)}")
                            print(f"   ✓ Extracted: {date_str}")
                            
                            for fmt in formats:
                                try:
                                    parsed_date = datetime.strptime(date_str, fmt).date()
                                    
                                    # Sanity checks
                                    if parsed_date > today:
                                        print(f"   ⚠️ Future date (skipping): {parsed_date}")
                                        continue
                                    
                                    if parsed_date < today - timedelta(days=1095):
                                        print(f"   ⚠️ Too old (skipping): {parsed_date}")
                                        continue
                                    
                                    # Valid date found!
                                    data['date'] = parsed_date
                                    data['confidence'] += 0.35  # Higher confidence with keyword
                                    date_found = True
                                    print(f"   ✅ DATE FOUND (with keyword): {parsed_date}")
                                    break
                                except ValueError:
                                    continue
                            
                            if date_found:
                                break
                                
                        except Exception as e:
                            continue
                    
                    if date_found:
                        break
            
            if date_found:
                break
        
        if date_found:
            break
    
    # If not found with keywords, try all patterns across entire text
    if not date_found:
        print(f"   🔍 No keyword found, searching entire text...")
        
        for pattern, extractor, formats, pattern_name in date_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    date_str = extractor(match)
                    print(f"   ✓ Pattern matched ({pattern_name}): {match.group(0)}")
                    print(f"   ✓ Extracted: {date_str}")
                    
                    for fmt in formats:
                        try:
                            parsed_date = datetime.strptime(date_str, fmt).date()
                            
                            if parsed_date > today:
                                continue
                            
                            if parsed_date < today - timedelta(days=1095):
                                continue
                            
                            data['date'] = parsed_date
                            data['confidence'] += 0.25  # Lower confidence without keyword
                            date_found = True
                            print(f"   ✅ DATE FOUND: {parsed_date}")
                            break
                        except ValueError:
                            continue
                    
                    if date_found:
                        break
                        
                except Exception as e:
                    continue
    
    # Final fallback: search first 10 lines for simple patterns
    if not date_found:
        print(f"   🔄 Fallback: searching first 10 lines...")
        
        for i, line in enumerate(lines[:10]):
            if any(x in line.lower() for x in ['total', 'amount', 'price', 'qty', 'quantity']):
                continue
            
            simple_patterns = [
                (r'(\d{1,2})[/-](\d{1,2})[/-](\d{4})', ['%m/%d/%Y', '%d/%m/%Y']),
                (r'(\d{1,2})\s+(\d{1,2})\s+(\d{4})', ['%m/%d/%Y', '%d/%m/%Y']),
            ]
            
            for pattern, formats in simple_patterns:
                match = re.search(pattern, line)
                if match:
                    date_str = match.group(0).replace(' ', '/').replace('-', '/')
                    for fmt in formats:
                        try:
                            parsed_date = datetime.strptime(date_str, fmt).date()
                            if today - timedelta(days=1095) <= parsed_date <= today:
                                data['date'] = parsed_date
                                data['confidence'] += 0.15
                                date_found = True
                                print(f"   ✅ FALLBACK: {parsed_date} from line {i}")
                                break
                        except:
                            continue
                if date_found:
                    break
            if date_found:
                break
    
    if not date_found:
        data['date'] = today
        print(f"   ⚠️ No date found, using today: {today}")

    # EXTRACT MERCHANT with enhanced detection
    known_merchants = [
        'Starbucks', 'Walmart', 'Wall-Mart', 'Target', 'Amazon', 'Costco',
        'McDonald\'s', 'Burger King', 'KFC', 'Subway', 'Domino\'s', 'Pizza Hut',
        'Shell', 'Chevron', 'Exxon', 'BP', 'Total', 'Caltex',
        'Whole Foods', 'Trader Joe\'s', 'Safeway', 'Kroger',
        'CVS', 'Walgreens', '7-Eleven', 'Circle K',
        'Supermarket', 'Burger Kingdom'
    ]
    
    for merchant in known_merchants:
        if merchant.lower() in text_lower:
            data['merchant'] = merchant
            data['confidence'] += 0.2
            print(f"🏪 MERCHANT: {merchant} (known brand)")
            break
    
    # If no known merchant, extract from top of receipt
    if not data['merchant']:
        for line in lines[:5]:  # Check first 5 lines
            clean = line.strip()
            # Skip header/info lines
            if len(clean) > 2 and not any(x in clean.upper() for x in [
                'RECEIPT', 'INVOICE', 'TEL', 'PHONE', 'FAX', 'ADDRESS', 
                'STREET', 'CITY', 'STATE', 'ZIP', 'WWW', '.COM', 'HTTP',
                'MANAGER', 'CASHIER', 'SERVER', 'THANK YOU'
            ]):
                # Skip if mostly numbers (phone, address)
                digit_ratio = sum(c.isdigit() for c in clean) / len(clean) if len(clean) > 0 else 0
                if digit_ratio < 0.5 and len(clean) <= 50:
                    data['merchant'] = clean.title()[:30]
                    print(f"🏪 MERCHANT: {data['merchant']} (extracted)")
                    break
    
    if not data['merchant']:
        data['merchant'] = "Unknown Merchant"
        print(f"🏪 MERCHANT: Unknown (default)")

    # SMART CATEGORY DETECTION based on merchant and keywords
    category_keywords = {
        'Food & Dining': [
            'restaurant', 'cafe', 'coffee', 'burger', 'pizza', 'sushi',
            'chinese', 'thai', 'italian', 'mexican', 'fast food',
            'starbucks', 'mcdonald', 'burger king', 'kfc', 'subway',
            'food', 'lunch', 'dinner', 'breakfast', 'meal'
        ],
        'Groceries': [
            'supermarket', 'grocery', 'market', 'walmart', 'target', 'costco',
            'whole foods', 'trader joe', 'safeway', 'kroger',
            'vegetables', 'fruits', 'meat', 'dairy'
        ],
        'Transportation': [
            'gas', 'fuel', 'petrol', 'diesel', 'shell', 'chevron', 'exxon', 'bp',
            'parking', 'toll', 'uber', 'lyft', 'taxi', 'transportation'
        ],
        'Shopping': [
            'store', 'mall', 'shop', 'clothing', 'fashion', 'electronics',
            'amazon', 'best buy', 'apple store'
        ],
    }
    
    for cat_name, keywords in category_keywords.items():
        if any(keyword in text_lower for keyword in keywords):
            cat = Category.objects.filter(
                user=user,
                category_name__icontains=cat_name.split()[0]
            ).first()
            if cat:
                data['category'] = cat
                data['confidence'] += 0.15
                print(f"📁 CATEGORY: {cat_name} (keyword match)")
                break
    
    if not data['category']:
        print(f"📁 CATEGORY: None (will use fallback)")

    # SMART PAYMENT DETECTION
    payment_indicators = {
        'Credit Card': ['visa', 'mastercard', 'amex', 'discover', 'credit', 'card'],
        'Cash': ['cash', 'cash payment'],
        'Bank Transfer': ['transfer', 'online payment', 'e-payment'],
    }
    
    for method, indicators in payment_indicators.items():
        if any(ind in text_lower for ind in indicators):
            data['payment_method'] = method
            print(f"💳 PAYMENT: {method}")
            break
    
    if not data['payment_method']:
        data['payment_method'] = 'Cash'
        print(f"💳 PAYMENT: Cash (default)")

    # Final confidence calculation
    data['confidence'] = min(data['confidence'], 1.0)
    
    print(f"\n{'='*70}")
    print(f"FINAL EXTRACTION:")
    print(f"  Amount: ${data['amount']}")
    print(f"  Date: {data['date']}")
    print(f"  Merchant: {data['merchant']}")
    print(f"  Category: {data['category'].category_name if data['category'] else 'None'}")
    print(f"  Payment: {data['payment_method']}")
    print(f"  Confidence: {data['confidence']:.1%}")
    print(f"{'='*70}\n")
    
    return data


def _smart_amount_detect(text):
    """
    Smart amount detection for voice/text input.
    Handles formats like: "$50", "50 dollars", "spent 50", "cost 50.99"
    """
    text_lower = text.lower().strip()
    
    # Pattern 1: Dollar sign formats ($50, $50.99)
    match = re.search(r'\$\s*(\d+(?:\.\d{2})?)', text)
    if match:
        try:
            amount = Decimal(match.group(1))
            if 0.01 <= amount <= 50000:
                print(f"💰 Amount detected: ${amount} (from ${match.group(0)})")
                return amount
        except:
            pass
    
    # Pattern 2: Number + "dollars" or "bucks" (50 dollars, 25.50 bucks)
    match = re.search(r'(\d+(?:\.\d{2})?)\s*(?:dollars?|bucks?|usd)', text_lower)
    if match:
        try:
            amount = Decimal(match.group(1))
            if 0.01 <= amount <= 50000:
                print(f"💰 Amount detected: ${amount} (from '{match.group(0)}')")
                return amount
        except:
            pass
    
    # Pattern 3: Action words + number (spent 50, cost 25.99, paid 100)
    match = re.search(r'(?:spent|cost|paid|price|total)\s*(?:of|was|is)?\s*\$?\s*(\d+(?:\.\d{2})?)', text_lower)
    if match:
        try:
            amount = Decimal(match.group(1))
            if 0.01 <= amount <= 50000:
                print(f"💰 Amount detected: ${amount} (from '{match.group(0)}')")
                return amount
        except:
            pass
    
    # Pattern 4: Just a number with 2 decimals (likely a price)
    match = re.search(r'\b(\d+\.\d{2})\b', text)
    if match:
        try:
            amount = Decimal(match.group(1))
            if 0.01 <= amount <= 50000:
                print(f"💰 Amount detected: ${amount} (standalone)")
                return amount
        except:
            pass
    
    # Pattern 5: Just a whole number (last resort)
    match = re.search(r'\b(\d+)\b', text)
    if match:
        try:
            amount = Decimal(match.group(1))
            if 1 <= amount <= 10000:
                print(f"💰 Amount detected: ${amount} (whole number)")
                return Decimal(f"{amount}.00")
        except:
            pass
    
    print("⚠️ No amount detected")
    return Decimal('0.00')


def _smart_category_detect(text, user):
    """
    Smart category detection for voice/text input.
    Detects category based on keywords and merchant names.
    """
    text_lower = text.lower().strip()
    
    # Category keyword mapping
    category_keywords = {
        'Food & Dining': [
            'food', 'lunch', 'dinner', 'breakfast', 'coffee', 'cafe', 'restaurant',
            'burger', 'pizza', 'sushi', 'chinese', 'thai', 'italian', 'mexican',
            'starbucks', 'mcdonald', 'burger king', 'kfc', 'subway', 'domino',
            'ate', 'meal', 'snack', 'drink', 'eat', 'dining'
        ],
        'Groceries': [
            'grocery', 'groceries', 'supermarket', 'walmart', 'target', 'costco',
            'market', 'store', 'shopping', 'bought', 'milk', 'bread', 'eggs',
            'vegetables', 'fruits', 'meat', 'cheese'
        ],
        'Transportation': [
            'gas', 'fuel', 'petrol', 'diesel', 'uber', 'lyft', 'taxi', 'grab',
            'parking', 'toll', 'bus', 'train', 'subway', 'metro', 'ride',
            'shell', 'chevron', 'exxon', 'bp', 'transport', 'commute'
        ],
        'Shopping': [
            'clothes', 'clothing', 'shirt', 'pants', 'shoes', 'dress', 'jacket',
            'amazon', 'online', 'bought', 'purchased', 'mall', 'store',
            'electronics', 'phone', 'laptop', 'gadget'
        ],
        'Entertainment': [
            'movie', 'cinema', 'theater', 'concert', 'show', 'game', 'sports',
            'netflix', 'spotify', 'subscription', 'gym', 'fitness'
        ],
        'Bills & Utilities': [
            'bill', 'electric', 'electricity', 'water', 'internet', 'wifi',
            'phone bill', 'utility', 'rent', 'mortgage', 'insurance'
        ],
        'Healthcare': [
            'doctor', 'hospital', 'pharmacy', 'medicine', 'medical', 'clinic',
            'dentist', 'prescription', 'drug', 'health'
        ],
    }
    
    # Check each category
    for category_name, keywords in category_keywords.items():
        if any(keyword in text_lower for keyword in keywords):
            # Try to find matching category in database
            cat = Category.objects.filter(
                user=user,
                category_name__icontains=category_name.split()[0]
            ).first()
            
            if cat:
                print(f"📁 Category detected: {category_name} (matched: {[k for k in keywords if k in text_lower]})")
                return cat
    
    print("⚠️ No category detected, using fallback")
    return None


def _smart_merchant_detect(text):
    """
    Smart merchant detection for voice/text input.
    """
    text_lower = text.lower().strip()
    
    # Common merchant names
    known_merchants = [
        'Starbucks', 'Walmart', 'Target', 'Amazon', 'Costco',
        'McDonald\'s', 'Burger King', 'KFC', 'Subway', 'Domino\'s',
        'Shell', 'Chevron', 'Uber', 'Lyft', 'Netflix', 'Spotify',
        'Whole Foods', 'Trader Joe\'s', 'Safeway', 'Kroger'
    ]
    
    for merchant in known_merchants:
        if merchant.lower() in text_lower:
            print(f"🏪 Merchant detected: {merchant}")
            return merchant
    
    # Try to extract "at [merchant]" or "from [merchant]"
    patterns = [
        r'(?:at|from|to)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)',
        r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s+(?:store|market|restaurant|cafe)',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            merchant = match.group(1).strip()
            if len(merchant) > 2:
                print(f"🏪 Merchant detected: {merchant}")
                return merchant
    
    print("⚠️ No merchant detected")
    return None


def _smart_date_detect(text):
    """
    Smart date detection for voice/text input.
    Handles: "yesterday", "today", "last Monday", "3 days ago", "12/15/2024"
    """
    text_lower = text.lower().strip()
    today = timezone.now().date()
    
    # Relative dates
    if 'today' in text_lower:
        print(f"📅 Date detected: {today} (today)")
        return today
    
    if 'yesterday' in text_lower:
        date = today - timedelta(days=1)
        print(f"📅 Date detected: {date} (yesterday)")
        return date
    
    # "X days ago"
    match = re.search(r'(\d+)\s*days?\s*ago', text_lower)
    if match:
        days_ago = int(match.group(1))
        date = today - timedelta(days=days_ago)
        print(f"📅 Date detected: {date} ({days_ago} days ago)")
        return date
    
    # Weekday names (last Monday, Tuesday, etc.)
    weekdays = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
    for idx, day in enumerate(weekdays):
        if day in text_lower:
            current_weekday = today.weekday()
            target_weekday = idx
            days_back = (current_weekday - target_weekday) % 7
            if days_back == 0:
                days_back = 7  # Last week's same day
            date = today - timedelta(days=days_back)
            print(f"📅 Date detected: {date} (last {day.title()})")
            return date
    
    # Explicit dates (12/15/2024, 2024-12-15)
    date_patterns = [
        (r'(\d{1,2})[/-](\d{1,2})[/-](\d{4})', ['%m/%d/%Y', '%d/%m/%Y']),
        (r'(\d{4})[/-](\d{1,2})[/-](\d{1,2})', ['%Y-%m-%d']),
    ]
    
    for pattern, formats in date_patterns:
        match = re.search(pattern, text)
        if match:
            date_str = match.group(0)
            for fmt in formats:
                try:
                    parsed_date = datetime.strptime(date_str, fmt).date()
                    if (today - timedelta(days=730)) <= parsed_date <= today:
                        print(f"📅 Date detected: {parsed_date} (explicit)")
                        return parsed_date
                except:
                    continue
    
    print(f"📅 Date defaulted to today: {today}")
    return today


def _smart_payment_detect(text):
    """
    Smart payment method detection for voice/text input.
    """
    text_lower = text.lower().strip()
    
    if any(word in text_lower for word in ['cash', 'paid cash']):
        print("💳 Payment: Cash")
        return 'Cash'
    
    if any(word in text_lower for word in ['card', 'credit', 'debit', 'visa', 'mastercard']):
        print("💳 Payment: Credit Card")
        return 'Credit Card'
    
    if any(word in text_lower for word in ['bank', 'transfer', 'online', 'paypal', 'venmo']):
        print("💳 Payment: Bank Transfer")
        return 'Bank Transfer'
    
    print("💳 Payment: Cash (default)")
    return 'Cash'


def _get_fallback_category(user):
    """Get or create Uncategorized category"""
    cat, _ = Category.objects.get_or_create(
        user=user, 
        category_name='Uncategorized', 
        defaults={'icon': '❓', 'color': '#6c757d'}
    )
    return cat


# ==========================================
#  VIEWS
# ==========================================

@login_required
def expense_list(request):
    expenses = Expense.objects.filter(user=request.user).order_by('-expense_date')
    return render(request, 'expenses/expense_list.html', {'expenses': expenses})

@login_required
def expense_create(request):
    if request.method == 'POST':
        form = ExpenseForm(request.POST)
        if form.is_valid():
            expense = form.save(commit=False)
            expense.user = request.user
            expense.save()
            check_budget_alerts(request.user)
            messages.success(request, 'Expense added successfully!')
            return redirect('expenses:list')
    else:
        form = ExpenseForm()
    return render(request, 'expenses/expense_form.html', {'form': form, 'title': 'Add Expense'})

@login_required
def expense_update(request, pk):
    expense = get_object_or_404(Expense, pk=pk, user=request.user)
    user_curr = request.user.preferences.currency if hasattr(request.user, 'preferences') else 'USD'
    
    if request.method == 'POST':
        form = ExpenseForm(request.POST, instance=expense)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.currency = user_curr
            obj.save()
            messages.success(request, 'Expense updated!')
            return redirect('expenses:list')
    else:
        initial = {}
        if expense.currency and expense.currency != user_curr:
            converted = convert_amount(expense.amount, expense.currency, user_curr)
            initial['amount'] = round(converted, 2)
        form = ExpenseForm(instance=expense, initial=initial)
    return render(request, 'expenses/expense_form.html', {'form': form, 'title': 'Edit Expense'})

@login_required
def expense_delete(request, pk):
    expense = get_object_or_404(Expense, pk=pk, user=request.user)
    if request.method == 'POST':
        expense.delete()
        messages.success(request, 'Expense deleted!')
        return redirect('expenses:list')
    return render(request, 'expenses/expense_confirm_delete.html', {'expense': expense})

@login_required
def expense_detail(request, pk):
    expense = get_object_or_404(Expense, pk=pk, user=request.user)
    return render(request, 'expenses/expense_detail.html', {'expense': expense})

@login_required
def receipt_upload(request):
    if request.method == 'POST' and request.FILES.get('receipt_file'):
        uploaded_file = request.FILES['receipt_file']
        
        try:
            reader = easyocr.Reader(['en'], gpu=False)
            file_bytes = uploaded_file.read()
            result_list = reader.readtext(file_bytes, detail=0)
            ocr_text = "\n".join(result_list)
            print(f"\n{'='*70}")
            print(f"OCR OUTPUT:")
            print(ocr_text)
            print(f"{'='*70}\n")
        except Exception as e:
            print(f"OCR Failed: {e}")
            messages.error(request, "Failed to read image.")
            return redirect('expenses:receipt_upload')

        extracted = _smart_extract(ocr_text, request.user)
        
        amount = extracted['amount'] or Decimal('0.00')
        merchant = extracted['merchant'] or "Scanned Receipt"
        category = extracted['category'] or _get_fallback_category(request.user)
        user_curr = request.user.preferences.currency if hasattr(request.user, 'preferences') else 'USD'

        with transaction.atomic():
            expense = Expense.objects.create(
                user=request.user,
                category=category,
                amount=amount,
                currency=user_curr,
                expense_date=extracted['date'],
                merchant_name=merchant,
                description=f"Scanned: {ocr_text[:100]}...",
                payment_method=extracted['payment_method'],
                entry_method='receipt_scan'
            )
            
            uploaded_file.seek(0)
            Receipt.objects.create(expense=expense, file=uploaded_file, ocr_text=ocr_text)
            
            AIExtraction.objects.create(
                expense=expense,
                raw_data={"text": ocr_text, "extracted": str(extracted)},
                confidence_score=extracted['confidence'],
                extraction_method='ocr_easyocr'
            )
            
            check_budget_alerts(request.user)

        if amount > 0:
            messages.success(request, f"✅ Found ${amount} at {merchant}")
        else:
            messages.warning(request, "⚠️ Could not find amount. Please verify.")
            
        return redirect('expenses:update', pk=expense.pk)

    return render(request, 'expenses/receipt_upload.html')

@login_required
def voice_input(request):
    """
    Voice input with smart extraction.
    Example: "I spent $45.50 at Starbucks for coffee yesterday"
    """
    if request.method == 'POST':
        text = request.POST.get('voice_text', '').strip()
        
        if not text:
            messages.error(request, "Please provide voice input text.")
            return redirect('expenses:voice_input')
        
        print(f"\n{'='*70}")
        print(f"VOICE INPUT: {text}")
        print(f"{'='*70}")
        
        # Smart extraction
        amount = _smart_amount_detect(text)
        category = _smart_category_detect(text, request.user)
        merchant = _smart_merchant_detect(text)
        date = _smart_date_detect(text)
        payment_method = _smart_payment_detect(text)
        
        # Fallbacks
        if not category:
            category = _get_fallback_category(request.user)
        
        if not merchant:
            merchant = "Voice Entry"
        
        user_curr = request.user.preferences.currency if hasattr(request.user, 'preferences') else 'USD'
        
        with transaction.atomic():
            expense = Expense.objects.create(
                user=request.user,
                category=category,
                amount=amount,
                currency=user_curr,
                expense_date=date,
                merchant_name=merchant,
                description=f"Voice: {text}",
                payment_method=payment_method,
                entry_method='voice_input'
            )
            check_budget_alerts(request.user)
        
        if amount > 0:
            messages.success(
                request, 
                f"✅ Voice entry saved: ${amount} at {merchant} on {date}"
            )
        else:
            messages.warning(
                request,
                "⚠️ Could not detect amount. Please edit the expense."
            )
        
        return redirect('expenses:update', pk=expense.pk)
    
    return render(request, 'expenses/voice_input.html')

@login_required
def text_parse(request):
    """
    Text parsing with smart extraction.
    Example: "Lunch at Burger King $25.50 yesterday with credit card"
    """
    if request.method == 'POST':
        text = request.POST.get('raw_text', '').strip()
        
        if not text:
            messages.error(request, "Please provide text input.")
            return redirect('expenses:text_parse')
        
        print(f"\n{'='*70}")
        print(f"TEXT INPUT: {text}")
        print(f"{'='*70}")
        
        # Smart extraction
        amount = _smart_amount_detect(text)
        category = _smart_category_detect(text, request.user)
        merchant = _smart_merchant_detect(text)
        date = _smart_date_detect(text)
        payment_method = _smart_payment_detect(text)
        
        # Fallbacks
        if not category:
            category = _get_fallback_category(request.user)
        
        if not merchant:
            merchant = "Quick Add"
        
        user_curr = request.user.preferences.currency if hasattr(request.user, 'preferences') else 'USD'
        
        with transaction.atomic():
            expense = Expense.objects.create(
                user=request.user,
                category=category,
                amount=amount,
                currency=user_curr,
                expense_date=date,
                merchant_name=merchant,
                description=f"Text: {text}",
                payment_method=payment_method,
                entry_method='text_parsing'
            )
            check_budget_alerts(request.user)
        
        if amount > 0:
            messages.success(
                request,
                f"✅ Text entry saved: ${amount} at {merchant} on {date}"
            )
        else:
            messages.warning(
                request,
                "⚠️ Could not detect amount. Please edit the expense."
            )
        
        return redirect('expenses:update', pk=expense.pk)
    
    return render(request, 'expenses/text_parse.html')