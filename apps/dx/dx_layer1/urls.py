from django.urls import path
from django.shortcuts import redirect
from . import views
from .api import views as api_views

app_name = 'layer1'

urlpatterns = [
    # Pages
    path('', views.index, name='index'),
    path('check-log/', lambda request: redirect('/dx/data/check-log/', permanent=True)),

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
    path('api/market-promotion-raw-data/', api_views.market_promotion_raw_data, name='api_market_promotion_raw_data'),
    path('api/backup/', api_views.backup_retail_data, name='api_backup'),
    path('api/backup-status/', api_views.backup_status, name='api_backup_status'),

    # Check Log API
    path('api/check/status/', api_views.check_status, name='api_check_status'),
    path('api/check/save/', api_views.check_save, name='api_check_save'),
    path('api/check/delete/', api_views.check_delete, name='api_check_delete'),
    path('api/check/log/', api_views.check_log_list, name='api_check_log_list'),
    path('api/check/memo/', api_views.check_memo_update, name='api_check_memo_update'),

]
