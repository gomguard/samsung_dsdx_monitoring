from django.http import JsonResponse
from datetime import datetime, timedelta
from apps.common.response import log_error
from . import market_trend_services as svc


def market_trend_raw_data(request):
    """
    Market Trend 원본 데이터 조회 API
    - category: TV 또는 HHP
    - content_type: search_volume, social_trend, news_trend 등
    - date: 조회 날짜 (YYYY-MM-DD)
    """
    category = request.GET.get('category', 'TV')
    content_type = request.GET.get('content_type', '')
    date_str = request.GET.get('date')

    if not date_str:
        target_date = (datetime.now() - timedelta(days=1)).date()
    else:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()

    try:
        result = svc.get_market_trend_raw_data(category, content_type, target_date)
        return JsonResponse(result)
    except Exception as e:
        return JsonResponse({'error': log_error(e)})
