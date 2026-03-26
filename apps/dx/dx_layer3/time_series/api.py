"""
시계열 이상치 API — HTTP 래퍼 (파라미터 파싱 + services 호출 + JsonResponse)
"""

from datetime import datetime, timedelta
from django.http import JsonResponse
from apps.common.db import dx_connection
from apps.common.response import safe_error, log_error
from . import services


def time_series_detail(request):
    """시계열 이상치 상세 API"""
    date_str = request.GET.get('date')
    detail_code = request.GET.get('detail_code', '')
    try:
        days = min(int(request.GET.get('days', 1)), 30)
    except (ValueError, TypeError):
        days = 1

    if not detail_code:
        return JsonResponse({'items': [], 'total': 0, 'anomaly_count': 0})

    if date_str:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    else:
        target_date = (datetime.now() - timedelta(days=1)).date()

    try:
        with dx_connection() as (conn, cursor):
            result = services.get_time_series_detail(cursor, target_date, detail_code, days)
            if 'error' in result:
                return JsonResponse(result, status=result.pop('status_code', 400))
            return JsonResponse(result)
    except Exception as e:
        log_error(e)
        return safe_error(e, items=[])


def duplicate_detail(request):
    """중복 변형 탐지 상세 API"""
    date_str = request.GET.get('date')
    product_line = request.GET.get('type', 'tv')

    if date_str:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    else:
        target_date = (datetime.now() - timedelta(days=1)).date()

    try:
        with dx_connection() as (conn, cursor):
            result = services.get_duplicate_detail(cursor, target_date, product_line)
            return JsonResponse(result)
    except Exception as e:
        return safe_error(e)


def review_change_detail(request):
    """리뷰 수 급변 상세 API"""
    date_str = request.GET.get('date')
    product_line = request.GET.get('type', 'tv')

    if date_str:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    else:
        target_date = (datetime.now() - timedelta(days=1)).date()

    try:
        with dx_connection() as (conn, cursor):
            result = services.get_review_change_detail(cursor, target_date, product_line)
            return JsonResponse(result)
    except Exception as e:
        return safe_error(e)


def price_anomalies(request):
    """가격 이상치 상세 조회 API"""
    date_str = request.GET.get('date')
    product_line = request.GET.get('type', 'tv')

    if date_str:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    else:
        target_date = (datetime.now() - timedelta(days=1)).date()

    try:
        with dx_connection() as (conn, cursor):
            result = services.get_price_anomalies(cursor, target_date, product_line)
            return JsonResponse(result)
    except Exception as e:
        return safe_error(e)


def price_changes(request):
    """급격한 가격 변동 조회 API"""
    date_str = request.GET.get('date')
    product_line = request.GET.get('type', 'tv')
    threshold = float(request.GET.get('threshold', 0.3))

    if date_str:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    else:
        target_date = (datetime.now() - timedelta(days=1)).date()

    try:
        with dx_connection() as (conn, cursor):
            result = services.get_price_changes(cursor, target_date, product_line, threshold)
            return JsonResponse(result)
    except Exception as e:
        return safe_error(e)
