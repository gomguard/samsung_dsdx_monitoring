from django.urls import path
from . import views
from .stats import stats_api

app_name = 'ds_layer3'

urlpatterns = [
    path('', views.index, name='index'),
    path('api/stats/', stats_api.layer_stats, name='api_stats'),
    path('api/sku-detail/', stats_api.sku_detail, name='api_sku_detail'),
    path('api/sku-history/', stats_api.sku_history, name='api_sku_history'),
]
