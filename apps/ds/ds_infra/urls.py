from django.urls import path
from . import views
from .api import views as api_views

app_name = 'ds_infra'

urlpatterns = [
    # Pages
    path('', views.index, name='index'),

    # API
    path('api/ec2-status/', api_views.ec2_status, name='api_ec2_status'),
    path('api/ec2-action/', api_views.ec2_action, name='api_ec2_action'),
]
