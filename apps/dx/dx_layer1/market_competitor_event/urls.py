from django.urls import path
from apps.dx.dx_layer1 import views as layer1_views
from . import market_competitor_event_api as api

urlpatterns = [
    path('', layer1_views.market_competitor_event, name='market_competitor_event'),
    path('api/raw-data/', api.market_competitor_event_raw_data, name='api_market_competitor_event_raw_data'),
    path('api/missing/', api.market_competitor_event_missing_keywords, name='api_market_competitor_event_missing'),
]
