from django.urls import path
from . import views
from .api import views as api_views

app_name = 'dx_report'

urlpatterns = [
    path('', views.index, name='index'),
    path('api/stats/', api_views.report_stats, name='api_stats'),
]
