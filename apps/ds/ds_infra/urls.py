from django.urls import path
from . import views
from . import infra_api

app_name = 'ds_infra'

urlpatterns = [
    # Pages
    path('', views.index, name='index'),

    # API
    path('api/ec2-status/', infra_api.ec2_status, name='api_ec2_status'),
    path('api/ec2-action/', infra_api.ec2_action, name='api_ec2_action'),
]