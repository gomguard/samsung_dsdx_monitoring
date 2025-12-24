from django.urls import path
from . import views
from .api import views as api_views

app_name = 'layer4'

urlpatterns = [
    path('', views.index, name='index'),
    path('api/stats/', api_views.layer_stats, name='api_stats'),
    path('api/sentiment/', api_views.sentiment_distribution, name='api_sentiment'),
    path('api/unanalyzed/', api_views.unanalyzed_items, name='api_unanalyzed'),
    path('api/retailer-sentiment/', api_views.retailer_sentiment, name='api_retailer_sentiment'),
]
