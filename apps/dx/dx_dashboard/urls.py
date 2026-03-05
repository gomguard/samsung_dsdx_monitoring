from django.urls import path
from . import views

app_name = 'dx_dashboard'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
]
