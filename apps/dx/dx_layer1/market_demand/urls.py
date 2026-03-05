from django.urls import path
from . import views
from . import api

urlpatterns = [
    path('', views.market_demand, name='market_demand'),
    path('api/raw-data/', api.market_demand_raw_data, name='api_market_demand_raw_data'),
    path('api/missing/', api.market_demand_missing_keywords, name='api_market_demand_missing'),
]
