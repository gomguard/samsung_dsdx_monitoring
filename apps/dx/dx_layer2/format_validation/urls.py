from django.urls import path
from . import views

urlpatterns = [
    path('', views.format_validation, name='format_validation'),
]
