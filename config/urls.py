"""
URL configuration for monitoring_dsdx project.
5단계 방어 체계 모니터링 시스템
"""

from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('apps.accounts.urls')),
    path('', include('apps.main.urls')),

    # DX (TV/HHP Retail) Layer URLs
    path('dx/layer1/', include('apps.layer1.urls', namespace='dx_layer1')),
    path('dx/layer2/', include('apps.layer2.urls', namespace='dx_layer2')),
    path('dx/layer3/', include('apps.layer3.urls', namespace='dx_layer3')),
    path('dx/layer4/', include('apps.layer4.urls', namespace='dx_layer4')),
    path('dx/layer5/', include('apps.layer5.urls', namespace='dx_layer5')),

    # DS (Global Price Tracking) Layer URLs
    path('ds/layer1/', include('apps.ds_layer1.urls')),
    path('ds/layer2/', include('apps.ds_layer2.urls')),
    path('ds/layer3/', include('apps.ds_layer3.urls')),

    # Report (보고용 페이지)
    path('ds/report/', include('apps.ds_report.urls')),

    # 기존 URL (하위 호환)
    path('layer1/', include('apps.layer1.urls')),
    path('layer2/', include('apps.layer2.urls')),
    path('layer3/', include('apps.layer3.urls')),
    path('layer4/', include('apps.layer4.urls')),
    path('layer5/', include('apps.layer5.urls')),
]
