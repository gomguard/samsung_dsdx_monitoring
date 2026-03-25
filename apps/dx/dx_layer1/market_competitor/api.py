from django.http import JsonResponse
from datetime import datetime, timedelta
from apps.common.db import dx_connection
from apps.common.response import log_error
from . import services


def market_competitor_keywords(request):
    """Market Competitor 키워드 등록 현황 API — market_mst 테이블"""
    category = request.GET.get('category', '')

    try:
        with dx_connection() as (conn, cursor):
            result = services.get_competitor_keywords(cursor, category)
            return JsonResponse(result)
    except Exception as e:
        return JsonResponse({'error': log_error(e)})


def market_competitor_raw_data(request):
    """Market Competitor Raw Data API — market_comp_product 테이블"""
    date_str = request.GET.get('date')
    category = request.GET.get('category', '')

    if date_str:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    else:
        target_date = (datetime.now() - timedelta(days=1)).date()

    try:
        with dx_connection() as (conn, cursor):
            result = services.get_competitor_raw_data(cursor, category, target_date)
            return JsonResponse(result)
    except Exception as e:
        return JsonResponse({'error': log_error(e)})
