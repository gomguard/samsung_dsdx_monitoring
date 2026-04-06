from django.urls import path
from apps.dx.dx_layer1 import views as layer1_views
from . import sentiment_api as api

urlpatterns = [
    path('', layer1_views.sentiment, name='sentiment'),
    path('api/stats/', api.sentiment_stats, name='api_sentiment'),
    path('api/raw-data/', api.sentiment_raw_data, name='api_sentiment_raw_data'),
]
