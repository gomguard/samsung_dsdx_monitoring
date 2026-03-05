from django.urls import path
from . import views
from . import api

urlpatterns = [
    path('', views.market_promotion, name='market_promotion'),
    path('api/raw-data/', api.market_promotion_raw_data, name='api_market_promotion_raw_data'),
]
