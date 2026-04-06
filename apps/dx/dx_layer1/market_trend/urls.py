from django.urls import path
from apps.dx.dx_layer1 import views as layer1_views
from . import market_trend_api as api

urlpatterns = [
    path('', layer1_views.market_trend, name='market_trend'),
    path('api/raw-data/', api.market_trend_raw_data, name='api_market_trend_raw_data'),
]
