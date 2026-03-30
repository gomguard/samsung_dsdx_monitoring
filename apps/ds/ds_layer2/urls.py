from django.urls import path
from . import views
from .stats import stats_api
from .report import report_api

app_name = 'ds_layer2'

urlpatterns = [
    path('', views.index, name='index'),

    # Stats Domain API
    path('api/stats/', stats_api.layer_stats, name='api_stats'),
    path('api/detail/', stats_api.table_null_detail, name='api_detail'),

    # Report Domain API
    path('api/status/', report_api.report_status, name='api_status'),
    path('api/save/', report_api.report_save, name='api_save'),
    path('api/delete/', report_api.report_delete, name='api_delete'),
]
