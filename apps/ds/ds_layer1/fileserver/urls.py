from django.urls import path
from . import api

urlpatterns = [
    path('api/fileserver/', api.fileserver_stats, name='api_fileserver'),
    path('api/fileserver-browse/', api.fileserver_browse, name='api_fileserver_browse'),
    path('api/fileserver-move/', api.fileserver_move, name='api_fileserver_move'),
]
