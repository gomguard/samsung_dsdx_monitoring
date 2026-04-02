from django.urls import path
from . import views
from . import api

urlpatterns = [
    path('', views.market_competitor_event, name='market_competitor_event'),
    path('api/raw-data/', api.market_competitor_event_raw_data, name='api_market_competitor_event_raw_data'),
    path('api/missing/', api.market_competitor_event_missing_keywords, name='api_market_competitor_event_missing'),
]
