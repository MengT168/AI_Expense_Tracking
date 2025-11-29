from django.urls import path
from . import views

app_name = 'categories'

urlpatterns = [
    path('', views.category_list, name='list'),
    path('add/', views.category_create, name='create'),
]