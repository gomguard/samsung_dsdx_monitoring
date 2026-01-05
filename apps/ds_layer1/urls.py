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
    path('api/table/', api_views.table_detail, name='api_table_detail'),
    path('api/range/', api_views.date_range_stats, name='api_date_range'),
    path('api/fileserver/', api_views.fileserver_stats, name='api_fileserver'),
]
