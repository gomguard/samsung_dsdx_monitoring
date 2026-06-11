from django.urls import path, include
from django.shortcuts import redirect
from apps.dx.dx_layer1.common import api as check_api

app_name = 'layer1'

urlpatterns = [
    path('', include('apps.dx.dx_layer1.dashboard.urls')),
    path('retail/', include('apps.dx.dx_layer1.retail.urls')),
    path('sentiment/', include('apps.dx.dx_layer1.sentiment.urls')),
    path('youtube/', include('apps.dx.dx_layer1.youtube.urls')),
    path('market-trend/', include('apps.dx.dx_layer1.market_trend.urls')),
    path('market-demand/', include('apps.dx.dx_layer1.market_demand.urls')),
    path('market-competitor/', include('apps.dx.dx_layer1.market_competitor.urls')),
    path('market-competitor-event/', include('apps.dx.dx_layer1.market_competitor_event.urls')),
    path('market-promotion/', include('apps.dx.dx_layer1.market_promotion.urls')),
    path('macro/', include('apps.dx.dx_layer1.macro.urls')),
    path('check-log/', lambda request: redirect('/dx/layer4/check-log/', permanent=True)),

    # 검수 확인/완료 API
    path('api/check/status/', check_api.check_status, name='api_check_status'),
    path('api/check/save/', check_api.check_save, name='api_check_save'),
    path('api/check/delete/', check_api.check_delete, name='api_check_delete'),
]
