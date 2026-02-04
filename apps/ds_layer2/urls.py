from django.urls import path
from . import views
from .api import views as api_views

app_name = 'ds_layer2'

urlpatterns = [
    path('', views.index, name='index'),
    path('report/', views.report, name='report'),
    path('api/stats/', api_views.layer_stats, name='api_stats'),
    path('api/detail/', api_views.table_null_detail, name='api_detail'),
    # 보고서 관리 API
    path('api/save/', api_views.report_save, name='api_save'),
    path('api/delete/', api_views.report_delete, name='api_delete'),
    path('api/update/', api_views.report_update, name='api_update'),
    path('api/daily-update/', api_views.report_daily_update, name='api_daily_update'),
    path('api/save-all/', api_views.report_save_all, name='api_save_all'),
    path('api/save-file-info/', api_views.report_save_file_info, name='api_save_file_info'),
    path('api/close/', api_views.report_close, name='api_close'),
    path('api/cancel-close/', api_views.report_cancel_close, name='api_cancel_close'),
    path('api/status/', api_views.report_status, name='api_status'),
    path('api/report-list/', api_views.report_list, name='api_report_list'),
    path('api/screenshot/', api_views.get_screenshot_url, name='api_screenshot'),
    # 스크린샷 캡쳐 API
    path('api/screenshot-capture/', api_views.screenshot_capture, name='api_screenshot_capture'),
    path('api/screenshot-status/', api_views.screenshot_status, name='api_screenshot_status'),
    # 파일 용량 히스토리 API
    path('api/file-size-history/', api_views.report_file_size_history, name='api_file_size_history'),
]
