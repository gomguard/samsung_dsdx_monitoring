from django.urls import path
from apps.dx.dx_layer1 import views as layer1_views
from . import market_promotion_api as api

urlpatterns = [
    path('', layer1_views.market_promotion, name='market_promotion'),
    path('api/raw-data/', api.market_promotion_raw_data, name='api_market_promotion_raw_data'),
]
