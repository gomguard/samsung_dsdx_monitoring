from django.urls import path
from . import views
from .api import views as api_views

app_name = 'layer3'

urlpatterns = [
    path('', views.index, name='index'),
    path('api/stats/', api_views.layer_stats, name='api_stats'),
    path('api/price-anomalies/', api_views.price_anomalies, name='api_price_anomalies'),
    path('api/price-changes/', api_views.price_changes, name='api_price_changes'),
]
