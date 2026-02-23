from django.urls import path
from . import views
from .api import views as api_views

app_name = 'layer2'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('null/', views.null_validation, name='null_validation'),
    path('format/', views.format_validation, name='format_validation'),
    path('anomaly/', views.anomaly_validation, name='anomaly_validation'),
    # DX APIs
    path('api/stats/', api_views.layer_stats, name='api_stats'),
    path('api/detail/', api_views.retailer_detail, name='api_detail'),
    path('api/null-detail/', api_views.null_detail, name='api_null_detail'),
    path('api/format-detail/', api_views.format_detail, name='api_format_detail'),
    path('api/anomaly-detail/', api_views.anomaly_detail, name='api_anomaly_detail'),
    path('api/format-rules/', api_views.format_rules, name='api_format_rules'),
    # DS APIs
    path('api/ds/stats/', api_views.ds_layer_stats, name='api_ds_stats'),
]
