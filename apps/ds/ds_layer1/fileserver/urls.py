from django.urls import path
from . import fileserver_api

urlpatterns = [
    path('api/fileserver/', fileserver_api.fileserver_stats, name='api_fileserver'),
    path('api/fileserver-browse/', fileserver_api.fileserver_browse, name='api_fileserver_browse'),
    path('api/fileserver-move/', fileserver_api.fileserver_move, name='api_fileserver_move'),
]
