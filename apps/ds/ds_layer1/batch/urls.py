from django.urls import path
from . import batch_api

urlpatterns = [
    path('api/batch/', batch_api.batch_list, name='api_batch_list'),
    path('api/batch/init/', batch_api.batch_init, name='api_batch_init'),
    path('api/batch/create/', batch_api.batch_create, name='api_batch_create'),
    path('api/batch/update/', batch_api.batch_update, name='api_batch_update'),
    path('api/batch/delete/', batch_api.batch_delete, name='api_batch_delete'),
]
