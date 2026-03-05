from django.urls import path
from . import views
from . import api

urlpatterns = [
    path('', views.market_trend, name='market_trend'),
    path('api/raw-data/', api.market_trend_raw_data, name='api_market_trend_raw_data'),
]
