from django.db import models
from django.conf import settings
from apps.expenses.models import Expense


class AIExtraction(models.Model):
    """AI processing records for expenses"""
    EXTRACTION_METHODS = [
        ('ocr_vision_api', 'OCR Vision API'),
        ('nlp_voice_processing', 'NLP Voice Processing'),
        ('nlp_text_parsing', 'NLP Text Parsing'),
    ]
    
    expense = models.ForeignKey(Expense, on_delete=models.CASCADE, related_name='ai_extractions')
    raw_data = models.JSONField()
    confidence_score = models.DecimalField(max_digits=3, decimal_places=2, default=0.00)
    extraction_method = models.CharField(max_length=50, choices=EXTRACTION_METHODS)
    processed_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'AI_EXTRACTION'
        ordering = ['-processed_at']
    
    def __str__(self):
        return f"AI Extraction for Expense #{self.expense.id}"


class AIInsight(models.Model):
    """AI-generated insights and recommendations"""
    INSIGHT_TYPES = [
        ('weekly_summary', 'Weekly Summary'),
        ('monthly_summary', 'Monthly Summary'),
        ('budget_alert', 'Budget Alert'),
        ('spending_pattern', 'Spending Pattern'),
        ('prediction', 'Prediction'),
        ('recommendation', 'Recommendation'),
    ]
    
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='ai_insights')
    insight_type = models.CharField(max_length=20, choices=INSIGHT_TYPES)
    insight_data = models.JSONField(null=True, blank=True)
    message = models.TextField()
    period_start = models.DateField(null=True, blank=True)
    period_end = models.DateField(null=True, blank=True)
    generated_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'AI_INSIGHT'
        ordering = ['-generated_at']
    
    def __str__(self):
        return f"{self.insight_type} for {self.user.email}"