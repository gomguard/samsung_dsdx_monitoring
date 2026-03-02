from django.urls import path
from . import views
from .api import views as api_views

app_name = 'dx_data'

urlpatterns = [
    # 페이지
    path('', views.index, name='index'),
    path('item-master/', views.item_master, name='item_master'),
    path('history/', views.history, name='history'),

    # API
    path('api/item-master/list/', api_views.item_master_list, name='api_item_master_list'),
    path('api/item-master/save/', api_views.item_master_save, name='api_item_master_save'),
    path('api/item-master/history/', api_views.item_master_history, name='api_item_master_history'),
]
