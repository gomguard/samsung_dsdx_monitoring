from django.urls import path
from . import views
from .api import views as api_views

app_name = 'ds_report'

urlpatterns = [
    path('', views.index, name='index'),
    path('api/stats/', api_views.report_stats, name='api_stats'),
    path('api/detail/', api_views.report_detail, name='api_detail'),
]
