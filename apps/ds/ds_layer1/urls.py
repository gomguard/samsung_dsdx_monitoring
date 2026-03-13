from django.urls import path, include
from . import views

app_name = 'ds_layer1'

urlpatterns = [
    # Pages
    path('', views.index, name='index'),
    path('fileserver/', views.fileserver, name='fileserver'),

    # API (모듈별 분리)
    path('', include('apps.ds.ds_layer1.collection.urls')),
    path('', include('apps.ds.ds_layer1.batch.urls')),
    path('', include('apps.ds.ds_layer1.fileserver.urls')),
    path('', include('apps.ds.ds_layer1.rerun.urls')),
]
