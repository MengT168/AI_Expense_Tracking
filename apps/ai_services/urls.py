from django.urls import path
from . import views

app_name = 'ai_services'

urlpatterns = [
    path('', views.insight_list, name='list'),
    path('generate/', views.trigger_analysis, name='generate'),
]