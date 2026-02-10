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
    path('api/fileserver/', api_views.fileserver_stats, name='api_fileserver'),

    # 크롤러 재실행 API
    path('api/rerun-crawler/', api_views.rerun_crawler, name='api_rerun_crawler'),

    # Batch management API
    path('api/batch/', api_views.batch_list, name='api_batch_list'),
    path('api/batch/init/', api_views.batch_init, name='api_batch_init'),
    path('api/batch/create/', api_views.batch_create, name='api_batch_create'),
    path('api/batch/update/', api_views.batch_update, name='api_batch_update'),
    path('api/batch/delete/', api_views.batch_delete, name='api_batch_delete'),
]
