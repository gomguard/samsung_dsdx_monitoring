from django.urls import path
from . import api

urlpatterns = [
    path('api/batch/', api.batch_list, name='api_batch_list'),
    path('api/batch/init/', api.batch_init, name='api_batch_init'),
    path('api/batch/create/', api.batch_create, name='api_batch_create'),
    path('api/batch/update/', api.batch_update, name='api_batch_update'),
    path('api/batch/delete/', api.batch_delete, name='api_batch_delete'),
]
