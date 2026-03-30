from django.urls import path
from . import views
from .report import report_api
from .screenshot import screenshot_api

app_name = 'ds_layer4'

urlpatterns = [
    path('', views.index, name='index'),

    # ==== 보고서(Report) 도메인 API ====
    path('api/update/', report_api.report_update, name='api_update'),
    path('api/daily-update/', report_api.report_daily_update, name='api_daily_update'),
    path('api/save-file-info/', report_api.report_save_file_info, name='api_save_file_info'),
    path('api/close/', report_api.report_close, name='api_close'),
    path('api/cancel-close/', report_api.report_cancel_close, name='api_cancel_close'),
    path('api/report-list/', report_api.report_list, name='api_report_list'),
    path('api/file-size-history/', report_api.report_file_size_history, name='api_file_size_history'),

    # ==== 스크린샷(Screenshot) 도메인 API ====
    path('api/screenshot/', screenshot_api.get_screenshot_url, name='api_screenshot'),
    path('api/screenshot-capture/', screenshot_api.screenshot_capture, name='api_screenshot_capture'),
    path('api/screenshot-status/', screenshot_api.screenshot_status, name='api_screenshot_status'),
    path('api/screenshot-delete/', screenshot_api.screenshot_delete, name='api_screenshot_delete'),
    path('api/screenshot-upload/', screenshot_api.screenshot_upload, name='api_screenshot_upload'),
]
