from django.urls import path
from apps.dx.dx_layer1 import views as layer1_views
from . import market_demand_api as api

urlpatterns = [
    path('', layer1_views.market_demand, name='market_demand'),
    path('api/raw-data/', api.market_demand_raw_data, name='api_market_demand_raw_data'),
    path('api/missing/', api.market_demand_missing_keywords, name='api_market_demand_missing'),
]
