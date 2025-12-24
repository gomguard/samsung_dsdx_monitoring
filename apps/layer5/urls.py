from django.urls import path
from . import views
from .api import views as api_views

app_name = 'layer5'

urlpatterns = [
    path('', views.index, name='index'),
    path('api/stats/', api_views.layer_stats, name='api_stats'),
    path('api/pending/', api_views.pending_items, name='api_pending'),
    path('api/quality/', api_views.quality_summary, name='api_quality'),
]
