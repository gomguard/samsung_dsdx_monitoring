from django.urls import path
from . import views
from . import api

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('api/stats/', api.layer_stats, name='api_stats'),
]
