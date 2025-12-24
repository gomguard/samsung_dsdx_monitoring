from django.urls import path
from . import views
from .api import views as api_views

app_name = 'ds_layer3'

urlpatterns = [
    path('', views.index, name='index'),
    path('api/stats/', api_views.layer_stats, name='api_stats'),
    path('api/recurring-detail/', api_views.recurring_detail, name='api_recurring_detail'),
]
