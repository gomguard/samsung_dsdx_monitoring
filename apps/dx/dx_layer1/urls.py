from django.urls import path
from django.shortcuts import redirect
from . import views
from .api import views as api_views
from apps.dx.dx_layer4.api import views as layer4_api_views

app_name = 'layer1'

urlpatterns = [
    # Pages
    path('', views.dashboard, name='dashboard'),
    path('retail/', views.retail, name='retail'),
    path('sentiment/', views.sentiment, name='sentiment'),
    path('youtube/', views.youtube, name='youtube'),
    path('market-trend/', views.market_trend, name='market_trend'),
    path('market-demand/', views.market_demand, name='market_demand'),
    path('market-competitor/', views.market_competitor, name='market_competitor'),
    path('market-competitor-event/', views.market_competitor_event, name='market_competitor_event'),
    path('market-promotion/', views.market_promotion, name='market_promotion'),
    path('check-log/', lambda request: redirect('/dx/layer4/check-log/', permanent=True)),

    # API
    path('api/stats/', api_views.layer_stats, name='api_stats'),
    path('api/retail/', api_views.retail_detail, name='api_retail_detail'),
    path('api/retail-summary/', api_views.retail_summary, name='api_retail_summary'),
    path('api/sentiment/', api_views.sentiment_stats, name='api_sentiment'),
    path('api/retailer-raw-data/', api_views.retailer_raw_data, name='api_retailer_raw_data'),
    path('api/retailer-columns/', api_views.retailer_columns_info, name='api_retailer_columns'),
    path('api/sentiment-raw-data/', api_views.sentiment_raw_data, name='api_sentiment_raw_data'),
    path('api/youtube-raw-data/', api_views.youtube_raw_data, name='api_youtube_raw_data'),
    path('api/market-trend-raw-data/', api_views.market_trend_raw_data, name='api_market_trend_raw_data'),
    path('api/market-demand-raw-data/', api_views.market_demand_raw_data, name='api_market_demand_raw_data'),
    path('api/market-demand-missing/', api_views.market_demand_missing_keywords, name='api_market_demand_missing'),
    path('api/market-competitor-keywords/', api_views.market_competitor_keywords, name='api_market_competitor_keywords'),
    path('api/market-competitor-raw-data/', api_views.market_competitor_raw_data, name='api_market_competitor_raw_data'),
    path('api/market-competitor-event-raw-data/', api_views.market_competitor_event_raw_data, name='api_market_competitor_event_raw_data'),
    path('api/market-promotion-raw-data/', api_views.market_promotion_raw_data, name='api_market_promotion_raw_data'),
    path('api/backup/', api_views.backup_retail_data, name='api_backup'),
    path('api/backup-status/', api_views.backup_status, name='api_backup_status'),

    # Check Log API — 코드는 Layer 4에 있고, Layer 1 페이지 호환을 위해 URL 유지
    path('api/check/status/', layer4_api_views.check_status, name='api_check_status'),
    path('api/check/save/', layer4_api_views.check_save, name='api_check_save'),
    path('api/check/delete/', layer4_api_views.check_delete, name='api_check_delete'),
    path('api/check/log/', layer4_api_views.check_log_list, name='api_check_log_list'),
    path('api/check/memo/', layer4_api_views.check_memo_update, name='api_check_memo_update'),

]
