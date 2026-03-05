from django.urls import path
from . import views
from . import api

urlpatterns = [
    path('', views.sentiment, name='sentiment'),
    path('api/stats/', api.sentiment_stats, name='api_sentiment'),
    path('api/raw-data/', api.sentiment_raw_data, name='api_sentiment_raw_data'),
]
