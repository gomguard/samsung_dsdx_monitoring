from django.urls import path
from . import views
from . import api

urlpatterns = [
    path('', views.retail, name='retail'),
    path('api/detail/', api.retail_detail, name='api_retail_detail'),
    path('api/summary/', api.retail_summary, name='api_retail_summary'),
    path('api/raw-data/', api.retailer_raw_data, name='api_retailer_raw_data'),
    path('api/columns/', api.retailer_columns_info, name='api_retailer_columns'),
    path('api/backup/', api.backup_retail_data, name='api_backup'),
    path('api/backup-status/', api.backup_status, name='api_backup_status'),
]
