from django.urls import path
from . import views
from .api import views as api_views

app_name = 'ds_layer4'

urlpatterns = [
    path('', views.index, name='index'),
    path('api/stats/', api_views.layer_stats, name='api_stats'),
]
