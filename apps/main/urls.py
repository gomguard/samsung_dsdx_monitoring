from django.urls import path
from . import views
from .api import views as api_views

app_name = 'main'

urlpatterns = [
    # Pages
    path('', views.index, name='index'),
    path('dx/', views.dx_dashboard, name='dx_dashboard'),
    path('dx/documents/', views.dx_documents, name='dx_documents'),
    path('dx/documents/new/', views.dx_document_edit, name='dx_document_new'),
    path('dx/documents/<str:document_id>/edit/', views.dx_document_edit, name='dx_document_edit'),
    path('ds/', views.ds_dashboard, name='ds_dashboard'),
    path('share/file/<path:token>/<str:file_name>', views.dx_document_share_file, name='dx_document_share_file'),
    path('share/<path:token>/', views.dx_document_share, name='dx_document_share'),

    # API
    path('api/dashboard/', api_views.dashboard_stats, name='api_dashboard'),
    path('api/dx/dashboard/', api_views.dx_dashboard_stats, name='api_dx_dashboard'),
    path('api/ds/dashboard/', api_views.ds_dashboard_stats, name='api_ds_dashboard'),
    path('api/schedule/', api_views.collection_schedule, name='api_schedule'),
    path('api/health/', api_views.health_check, name='api_health'),

    # Document API
    path('api/dx/documents/', api_views.dx_documents_list, name='api_dx_documents_list'),
    path('api/dx/documents/detail/', api_views.dx_document_detail, name='api_dx_document_detail'),
    path('api/dx/documents/create/', api_views.dx_document_create, name='api_dx_document_create'),
    path('api/dx/documents/<str:document_id>/update/', api_views.dx_document_update, name='api_dx_document_update'),
    path('api/dx/documents/<str:document_id>/delete/', api_views.dx_document_delete, name='api_dx_document_delete'),
    path('api/dx/documents/upload/', api_views.dx_document_upload, name='api_dx_document_upload'),
    path('api/dx/documents/files/', api_views.dx_document_files, name='api_dx_document_files'),
    path('api/dx/documents/files/<str:file_id>/delete/', api_views.dx_document_file_delete, name='api_dx_document_file_delete'),
    path('api/dx/documents/file/<str:file_name>', api_views.dx_document_file, name='api_dx_document_file'),
    path('api/dx/documents/share-token/', api_views.dx_document_share_token, name='api_dx_document_share_token'),
    path('api/dx/documents/share-list/', api_views.dx_document_share_list, name='api_dx_document_share_list'),
    path('api/dx/documents/share-revoke/', api_views.dx_document_share_revoke, name='api_dx_document_share_revoke'),
]
