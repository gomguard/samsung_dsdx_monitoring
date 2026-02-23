from django.urls import path
from . import views
from .api import views as api_views

app_name = 'ds_document'

urlpatterns = [
    # Pages
    path('ds/documents/', views.index, name='index'),
    path('ds/documents/new/', views.edit, name='new'),
    path('ds/documents/<str:document_id>/edit/', views.edit, name='edit'),
    path('ds-share/file/<path:token>/<str:file_name>', views.share_file, name='share_file'),
    path('ds-share/<path:token>/', views.share, name='share'),

    # Document API
    path('api/ds/documents/list/', api_views.documents_list, name='api_list'),
    path('api/ds/documents/detail/', api_views.document_detail, name='api_detail'),
    path('api/ds/documents/create/', api_views.document_create, name='api_create'),
    path('api/ds/documents/<str:document_id>/update/', api_views.document_update, name='api_update'),
    path('api/ds/documents/<str:document_id>/delete/', api_views.document_delete, name='api_delete'),
    path('api/ds/documents/upload/', api_views.upload, name='api_upload'),
    path('api/ds/documents/files/', api_views.document_files, name='api_files'),
    path('api/ds/documents/files/<str:file_id>/delete/', api_views.file_delete, name='api_file_delete'),
    path('api/ds/documents/file/<str:file_name>', api_views.file_proxy, name='api_file'),
    path('api/ds/documents/share-token/', api_views.share_token, name='api_share_token'),
    path('api/ds/documents/share-list/', api_views.share_list, name='api_share_list'),
    path('api/ds/documents/share-revoke/', api_views.share_revoke, name='api_share_revoke'),
]
