from django.urls import path
from apps.dx.dx_layer1 import views as layer1_views
from . import macro_api as api

urlpatterns = [
    path('', layer1_views.macro, name='macro'),
    path('api/raw-data/', api.macro_raw_data, name='api_macro_raw_data'),
]
