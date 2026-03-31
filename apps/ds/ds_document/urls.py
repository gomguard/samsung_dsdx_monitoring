from django.urls import path
from . import views
from .document import document_api

app_name = 'ds_document'

urlpatterns = [
    # Pages
    path('ds/documents/', views.index, name='index'),
    path('ds/documents/new/', views.edit, name='new'),
    path('ds/documents/<str:document_id>/edit/', views.edit, name='edit'),
    path('ds-share/file/<path:token>/<str:file_name>', views.share_file, name='share_file'),
    path('ds-share/<path:token>/', views.share, name='share'),

    # Document API
    path('api/ds/documents/list/', document_api.documents_list, name='api_list'),
    path('api/ds/documents/detail/', document_api.document_detail, name='api_detail'),
    path('api/ds/documents/create/', document_api.document_create, name='api_create'),
    path('api/ds/documents/<str:document_id>/update/', document_api.document_update, name='api_update'),
    path('api/ds/documents/<str:document_id>/delete/', document_api.document_delete, name='api_delete'),
    path('api/ds/documents/upload/', document_api.upload, name='api_upload'),
    path('api/ds/documents/files/', document_api.document_files, name='api_files'),
    path('api/ds/documents/files/<str:file_id>/delete/', document_api.file_delete, name='api_file_delete'),
    path('api/ds/documents/file/<str:file_name>', document_api.file_proxy, name='api_file'),
    path('api/ds/documents/share-token/', document_api.share_token, name='api_share_token'),
    path('api/ds/documents/share-list/', document_api.share_list, name='api_share_list'),
    path('api/ds/documents/share-revoke/', document_api.share_revoke, name='api_share_revoke'),
]
