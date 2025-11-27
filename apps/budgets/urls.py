# apps/budgets/urls.py
from django.urls import path
from . import views

app_name = 'budgets'  # This registers the namespace!

urlpatterns = [
    path('', views.budget_list, name='list'),
    path('add/', views.budget_create, name='create'),
]