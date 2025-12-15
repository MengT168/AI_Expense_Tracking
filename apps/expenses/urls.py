from django.urls import path
from . import views

app_name = 'expenses'

urlpatterns = [
    path('', views.expense_list, name='list'),
    path('add/', views.expense_create, name='create'),
    # path('<int:pk>/', views.expense_detail, name='detail'),
    path('<int:pk>/edit/', views.expense_update, name='update'),
    path('<int:pk>/delete/', views.expense_delete, name='delete'),
    path('upload-receipt/', views.receipt_upload, name='receipt_upload'),
    path('voice-input/', views.voice_input, name='voice_input'),
    path('text-parse/', views.text_parse, name='text_parse'),
        # Receipt Scan Flow
    path('create/receipt/', views.receipt_upload, name='receipt_upload'),
    path('review/<int:pk>/', views.receipt_review, name='review_receipt'),
    path('detail/<int:pk>/', views.expense_detail, name='detail'), 
    
]