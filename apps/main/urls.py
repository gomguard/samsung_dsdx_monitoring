from django.urls import path
from . import views
from .api import views as api_views

app_name = 'main'

urlpatterns = [
    # Pages
    path('', views.index, name='index'),
    path('ds/', views.ds_dashboard, name='ds_dashboard'),

    # API
    path('api/dashboard/', api_views.dashboard_stats, name='api_dashboard'),
    path('api/schedule/', api_views.collection_schedule, name='api_schedule'),
    path('api/health/', api_views.health_check, name='api_health'),
]
