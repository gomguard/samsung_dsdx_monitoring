from django.http import JsonResponse
from datetime import datetime, timedelta
from apps.common.db import dx_connection
from apps.common.response import log_error
from . import services


def market_competitor_event_raw_data(request):
    """Market Competitor Event Raw Data API — market_comp_event 테이블"""
    date_str = request.GET.get('date')
    category = request.GET.get('category', '')

    if date_str:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    else:
        target_date = (datetime.now() - timedelta(days=1)).date()

    try:
        with dx_connection() as (conn, cursor):
            result = services.get_competitor_event_raw_data(cursor, category, target_date)
            return JsonResponse(result)
    except Exception as e:
        return JsonResponse({'error': log_error(e)})


def market_competitor_event_missing_keywords(request):
    """Market Competitor Event 부족 키워드 상세 API"""
    date_str = request.GET.get('date')
    category = request.GET.get('category', 'all')

    if date_str:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    else:
        target_date = (datetime.now() - timedelta(days=1)).date()

    try:
        with dx_connection() as (conn, cursor):
            result = services.get_missing_keywords(cursor, category, target_date)
            return JsonResponse(result)
    except Exception as e:
        return JsonResponse({'error': log_error(e)})
