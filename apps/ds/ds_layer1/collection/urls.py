from django.urls import path
from . import api

urlpatterns = [
    path('api/stats/', api.layer_stats, name='api_stats'),
    path('api/instances/', api.instances_stats, name='api_instances'),
    path('api/table/', api.table_detail, name='api_table_detail'),
]
