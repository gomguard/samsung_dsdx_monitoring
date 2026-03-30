from django.urls import path
from . import rerun_api

urlpatterns = [
    path('api/rerun-crawler/', rerun_api.rerun_crawler, name='api_rerun_crawler'),
]
