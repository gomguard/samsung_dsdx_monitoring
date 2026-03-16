from django.urls import path
from . import views
from .api import views as api_views

app_name = 'ds_layer2'

urlpatterns = [
    path('', views.index, name='index'),
    path('api/stats/', api_views.layer_stats, name='api_stats'),
    path('api/detail/', api_views.table_null_detail, name='api_detail'),
    path('api/status/', api_views.report_status, name='api_status'),
    # 리테일러 마감 API
    path('api/save/', api_views.report_save, name='api_save'),
    path('api/delete/', api_views.report_delete, name='api_delete'),
]
