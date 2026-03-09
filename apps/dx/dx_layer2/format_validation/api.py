"""
형식 검증 API — HTTP 래퍼 (파라미터 파싱 + DB 연결 관리)
"""

from django.http import JsonResponse
from apps.common.db import get_dx_connection
from apps.common.response import safe_error, log_error
from apps.common.params import parse_date
from .services import (
    VALID_TABLES_FORMAT,
    VALID_TABLES_RULES,
    get_format_detail,
    get_format_rules,
)


def format_detail(request):
    """형식 오류 상세 조회 API"""
    target_date = parse_date(request.GET.get('date'))
    if target_date is None:
        return JsonResponse({'error': '날짜 형식이 올바르지 않습니다.'}, status=400)
    table = request.GET.get('table', 'tv_retail')
    if table not in VALID_TABLES_FORMAT:
        return JsonResponse({'error': '잘못된 테이블 파라미터'}, status=400)
    retailer = request.GET.get('retailer')
    try:
        days = max(1, int(request.GET.get('days', 1)))
    except (ValueError, TypeError):
        days = 1

    conn = None
    cursor = None
    try:
        conn = get_dx_connection()
        cursor = conn.cursor()
        data = get_format_detail(cursor, target_date, table, retailer, days)
        return JsonResponse(data)
    except Exception as e:
        return safe_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def format_rules(request):
    """형식검증 규칙 조회 API - DB 기반 (신규 테이블)"""
    table_name = request.GET.get('table', 'tv_retail_com')
    if table_name not in VALID_TABLES_RULES:
        return JsonResponse({'error': '잘못된 테이블 파라미터'}, status=400)
    retailer = request.GET.get('retailer', 'Amazon')

    conn = None
    cursor = None
    try:
        conn = get_dx_connection()
        cursor = conn.cursor()
        data = get_format_rules(cursor, table_name, retailer)
        return JsonResponse(data)
    except Exception as e:
        log_error(e, 'db')
        return JsonResponse({'rules': []})
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
