from django.urls import path
from . import collection_api

urlpatterns = [
    path('api/stats/', collection_api.layer_stats, name='api_stats'),
    path('api/instances/', collection_api.instances_stats, name='api_instances'),
    path('api/table/', collection_api.table_detail, name='api_table_detail'),
]
