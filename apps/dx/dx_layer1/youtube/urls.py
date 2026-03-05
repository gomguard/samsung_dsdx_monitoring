from django.urls import path
from . import views
from . import api

urlpatterns = [
    path('', views.youtube, name='youtube'),
    path('api/raw-data/', api.youtube_raw_data, name='api_youtube_raw_data'),
]
