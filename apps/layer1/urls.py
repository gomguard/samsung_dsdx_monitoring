from django.urls import path
from . import views
from .api import views as api_views

app_name = 'layer1'

urlpatterns = [
    # Pages
    path('', views.index, name='index'),

    # API
    path('api/stats/', api_views.layer_stats, name='api_stats'),
    path('api/retail/', api_views.retail_detail, name='api_retail_detail'),
    path('api/sentiment/', api_views.sentiment_stats, name='api_sentiment'),
]
