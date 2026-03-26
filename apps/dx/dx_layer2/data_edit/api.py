"""
data_edit API — HTTP 래퍼
connection/cursor 관리, 파라미터 파싱/검증, JsonResponse 반환
"""

import re
import json
from django.http import JsonResponse
from apps.common.db import dx_connection
from apps.common.response import safe_error
from . import services
from .services import VALID_TABLES_UPDATE


def update_cell(request):
    """셀 값 수정 API (POST)"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST only'}, status=405)

    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': '잘못된 요청 형식'}, status=400)

    table_name = body.get('table_name', '')
    try:
        row_id = int(body.get('row_id'))
    except (ValueError, TypeError):
        return JsonResponse({'error': '잘못된 ID 형식'}, status=400)
    column_name = body.get('column_name', '')
    new_value = body.get('new_value')
    crawl_date = body.get('crawl_date')
    correction_type = body.get('correction_type', 'null')
    memo = body.get('memo', '') or None

    # 필수 파라미터 검증
    if not all([table_name, row_id, column_name]):
        return JsonResponse({'error': '필수 파라미터 누락'}, status=400)

    # 테이블 화이트리스트 검증
    if table_name not in VALID_TABLES_UPDATE:
        return JsonResponse({'error': '수정 불가능한 테이블'}, status=400)

    # 컬럼명 안전성 검증 (영문, 숫자, 언더스코어만)
    if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', column_name):
        return JsonResponse({'error': '잘못된 컬럼명'}, status=400)

    username = request.user.username if request.user.is_authenticated else 'anonymous'

    try:
        with dx_connection() as (conn, cursor):
            result = services.update_cell_value(
                cursor, conn, table_name, row_id, column_name, new_value,
                crawl_date, correction_type, username, memo
            )

            # 서비스에서 에러 반환 시 처리
            if 'error' in result:
                return JsonResponse({'error': result['error']}, status=result.get('status', 400))

            conn.commit()
            return JsonResponse(result)
    except Exception as e:
        return safe_error(e)


def review_reasons(request):
    """정상 처리 이유 목록 조회 API (GET)"""
    check_type = request.GET.get('check_type', 'null_check')
    result = services.get_review_reasons(check_type)
    return JsonResponse(result)
