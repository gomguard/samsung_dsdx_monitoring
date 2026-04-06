from django.urls import path
from apps.dx.dx_layer1 import views as layer1_views
from . import youtube_api as api

urlpatterns = [
    path('', layer1_views.youtube, name='youtube'),
    path('api/raw-data/', api.youtube_raw_data, name='api_youtube_raw_data'),
]
