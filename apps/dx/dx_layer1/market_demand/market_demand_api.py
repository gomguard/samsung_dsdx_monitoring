from django.http import JsonResponse
from datetime import datetime, timedelta
from apps.common.response import log_error
from . import market_demand_services as svc


def market_demand_raw_data(request):
    """Market 수요증감율 Raw Data API"""
    date_str = request.GET.get('date')
    category = request.GET.get('category', 'TV')

    if date_str:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    else:
        target_date = (datetime.now() - timedelta(days=1)).date()

    try:
        result = svc.get_market_demand_raw_data(category, target_date)
        return JsonResponse(result)
    except Exception as e:
        return JsonResponse({'error': log_error(e)})


def market_demand_missing_keywords(request):
    """Market 수요증감율 부족 키워드 상세 API (openai_keywords 기준)"""
    date_str = request.GET.get('date')
    category = request.GET.get('category', 'all')

    if date_str:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    else:
        target_date = (datetime.now() - timedelta(days=1)).date()

    try:
        result = svc.get_missing_keywords(category, target_date)
        return JsonResponse(result)
    except Exception as e:
        return JsonResponse({'error': log_error(e)})
