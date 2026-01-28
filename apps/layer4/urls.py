from django.urls import path
from . import views
from .api import views as api_views

app_name = 'layer4'

urlpatterns = [
    path('', views.index, name='index'),
    path('api/status/', api_views.layer4_status, name='api_status'),
    path('api/save-suspicious/', api_views.save_suspicious, name='api_save_suspicious'),
    path('api/start-analysis/', api_views.start_analysis, name='api_start_analysis'),
    path('api/cases/', api_views.get_cases, name='api_cases'),
]
