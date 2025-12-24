from django.urls import path
from . import views
from .api import views as api_views

app_name = 'ds_layer1'

urlpatterns = [
    # Pages
    path('', views.index, name='index'),

    # API
    path('api/stats/', api_views.layer_stats, name='api_stats'),
    path('api/instances/', api_views.instances_stats, name='api_instances'),
]
