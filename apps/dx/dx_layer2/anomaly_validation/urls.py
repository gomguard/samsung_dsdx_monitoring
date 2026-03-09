from django.urls import path
from . import views

urlpatterns = [
    path('', views.anomaly_validation, name='anomaly_validation'),
]
