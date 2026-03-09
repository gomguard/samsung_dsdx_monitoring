from django.urls import path
from . import views

urlpatterns = [
    path('', views.null_validation, name='null_validation'),
]
