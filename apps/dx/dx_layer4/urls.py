from django.urls import path
from . import views
from .api import views as api_views
from apps.dx.dx_layer1.common import api as check_api

app_name = 'layer4'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('check-log/', views.check_log, name='check_log'),
    path('check-log/detail/', views.check_log_detail, name='check_log_detail'),
    path('corrections/', views.corrections, name='corrections'),
    path('report/', views.report, name='report'),
    # APIs
    path('api/dashboard-stats/', api_views.dashboard_stats, name='api_dashboard_stats'),
    path('api/corrections/', api_views.corrections_list, name='api_corrections'),
    path('api/corrections/cancel/', api_views.corrections_cancel, name='api_corrections_cancel'),
    path('api/report/', api_views.report_data, name='api_report'),
    path('api/review-reasons/', api_views.review_reasons, name='api_review_reasons'),
    # Check Log APIs — status는 Layer 1 common 참조, log/memo는 Layer 4 자체
    path('api/check/status/', check_api.check_status, name='api_check_status'),
    path('api/check/log/', api_views.check_log_list, name='api_check_log_list'),
    path('api/check/memo/', api_views.check_memo_update, name='api_check_memo_update'),
    # Collection Issues APIs
    path('api/collection-issues/', api_views.collection_issues_list, name='api_collection_issues'),
    path('api/collection-issues/save/', api_views.collection_issue_save, name='api_collection_issue_save'),
    path('api/collection-issues/delete/', api_views.collection_issue_delete, name='api_collection_issue_delete'),
    path('api/collection-issues/resolve/', api_views.collection_issue_resolve, name='api_collection_issue_resolve'),
]
