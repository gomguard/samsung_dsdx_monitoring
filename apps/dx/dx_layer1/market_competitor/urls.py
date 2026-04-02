from django.urls import path
from . import views
from . import api

urlpatterns = [
    path('', views.market_competitor, name='market_competitor'),
    path('api/keywords/', api.market_competitor_keywords, name='api_market_competitor_keywords'),
    path('api/raw-data/', api.market_competitor_raw_data, name='api_market_competitor_raw_data'),
    path('api/missing/', api.market_competitor_missing_keywords, name='api_market_competitor_missing'),
]
