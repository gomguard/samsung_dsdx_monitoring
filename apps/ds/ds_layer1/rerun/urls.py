from django.urls import path
from . import api

urlpatterns = [
    path('api/rerun-crawler/', api.rerun_crawler, name='api_rerun_crawler'),
]
