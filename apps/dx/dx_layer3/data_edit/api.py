import re
import json
from datetime import datetime

from django.http import JsonResponse

from apps.common.db import get_dx_connection
from apps.common.retail_columns import get_editable_columns
from apps.common.response import safe_error


VALID_TABLES_UPDATE = {
    'tv_retail_com', 'hhp_retail_com',
    'youtube_collection_logs', 'youtube_videos', 'youtube_comments',
    'market_trend', 'market_comp_product', 'market_comp_event', 'openai_forecast_results',
}


def update_cell(request):
    """셀 값 수정 API (POST) — Layer3 크로스필드"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST only'}, status=405)

    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': '잘못된 요청 형식'}, status=400)

    table_name = body.get('table_name', '')
    row_id = body.get('row_id')
    column_name = body.get('column_name', '')
    new_value = body.get('new_value')
    crawl_date = body.get('crawl_date')
    memo = body.get('memo', '') or None
    rule_id = body.get('rule_id')
    correction_type = body.get('correction_type', 'cross_field')
    if correction_type not in ('cross_field', 'field_missing'):
        correction_type = 'cross_field'

    if not all([table_name, row_id, column_name]):
        return JsonResponse({'error': '필수 파라미터 누락'}, status=400)

    if table_name not in VALID_TABLES_UPDATE:
        return JsonResponse({'error': '수정 불가능한 테이블'}, status=400)

    if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', column_name):
        return JsonResponse({'error': '잘못된 컬럼명'}, status=400)

    product_line = 'tv' if table_name == 'tv_retail_com' else 'hhp'

    conn = None
    try:
        conn = get_dx_connection()
        cursor = conn.cursor()

        cursor.execute(
            f"SELECT {column_name}, account_name, item FROM {table_name} WHERE id = %s",
            (row_id,)
        )
        row = cursor.fetchone()
        if not row:
            cursor.close()
            conn.close()
            return JsonResponse({'error': '해당 레코드가 없습니다'}, status=404)

        old_value = row[0]
        retailer = row[1]
        item_value = str(row[2]) if row[2] else ''

        editable_cols = get_editable_columns(product_line, retailer)
        if column_name not in editable_cols:
            cursor.close()
            conn.close()
            return JsonResponse({'error': f'{column_name} 컬럼은 수정할 수 없습니다'}, status=403)

        old_str = str(old_value) if old_value is not None else ''
        new_str = str(new_value) if new_value is not None else ''
        if old_str == new_str:
            cursor.close()
            conn.close()
            return JsonResponse({'success': True, 'message': '변경 없음'})

        update_value = new_value if new_value != '' else None
        cursor.execute(
            f"UPDATE {table_name} SET {column_name} = %s WHERE id = %s",
            (update_value, row_id)
        )

        now = datetime.now()
        user_id = request.user.username if request.user.is_authenticated else 'anonymous'
        cursor.execute("""
            INSERT INTO monitoring_corrections
                (layer, correction_type, table_name, record_id, column_name,
                 old_value, new_value, crawl_date, created_id, created_at, status, memo, retailer, item, rule_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            3, correction_type, table_name, row_id, column_name,
            str(old_value) if old_value is not None else None,
            str(new_value) if new_value is not None else None,
            crawl_date, user_id, now, 'corrected', memo, retailer, item_value or None, rule_id
        ))

        conn.commit()
        cursor.close()
        conn.close()

        return JsonResponse({'success': True, 'old_value': old_str, 'new_value': new_str})

    except Exception as e:
        if conn:
            try:
                conn.rollback()
                conn.close()
            except Exception:
                pass
        return safe_error(e)


def review_reasons(request):
    """정상 처리 이유 목록 조회 API (GET)"""
    from apps.common.constants import get_reasons
    check_type = request.GET.get('check_type', 'cross_field')
    reasons = [{'text': r} for r in get_reasons(check_type)]
    return JsonResponse({'success': True, 'reasons': reasons})


def review(request):
    """크로스필드/누락필드 정상 처리 API (POST)"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST only'}, status=405)

    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': '잘못된 요청 형식'}, status=400)

    table_name = body.get('table_name', '')
    record_id = body.get('record_id')
    column_name = body.get('column_name', '')
    status = body.get('status', '')
    memo = body.get('memo', '')
    reason = body.get('reason', '')
    crawl_date = body.get('crawl_date')
    rule_id = body.get('rule_id')
    correction_type = body.get('correction_type', 'cross_field')
    if correction_type not in ('cross_field', 'field_missing'):
        correction_type = 'cross_field'

    if not all([table_name, record_id, column_name, status]):
        return JsonResponse({'error': '필수 파라미터 누락'}, status=400)

    # 정상 처리만 허용 (reverted 불가)
    if status != 'normal':
        return JsonResponse({'error': '잘못된 status 값'}, status=400)

    if not reason:
        return JsonResponse({'error': '이유 선택은 필수입니다'}, status=400)

    if table_name not in VALID_TABLES_UPDATE:
        return JsonResponse({'error': '허용되지 않는 테이블'}, status=400)

    if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', column_name):
        return JsonResponse({'error': '잘못된 컬럼명'}, status=400)

    conn = None
    try:
        conn = get_dx_connection()
        cursor = conn.cursor()

        # 현재 값 + account_name + item 조회
        cursor.execute(
            f"SELECT {column_name}, account_name, item FROM {table_name} WHERE id = %s",
            (record_id,)
        )
        row = cursor.fetchone()
        if not row:
            cursor.close()
            conn.close()
            return JsonResponse({'error': '해당 레코드가 없습니다'}, status=404)

        old_value = row[0]
        retailer = row[1]
        item_value = str(row[2]) if row[2] else None

        # 중복 정상처리 체크
        cursor.execute("""
            SELECT id FROM monitoring_corrections
            WHERE table_name = %s AND record_id = %s AND column_name = %s
              AND correction_type = %s AND status = 'normal' AND crawl_date = %s
        """, (table_name, record_id, column_name, correction_type, str(crawl_date)))
        if cursor.fetchone():
            cursor.close()
            conn.close()
            return JsonResponse({'error': '이미 정상처리된 항목입니다'}, status=400)

        now = datetime.now()
        user_id = request.user.username if request.user.is_authenticated else 'anonymous'

        cursor.execute("""
            INSERT INTO monitoring_corrections
                (layer, correction_type, table_name, record_id, column_name,
                 old_value, new_value, crawl_date, created_id, created_at, status, memo, reason, retailer, item, rule_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            3, correction_type, table_name, record_id, column_name,
            str(old_value) if old_value is not None else None,
            None,
            crawl_date, user_id, now, status, memo or None,
            reason or None, retailer or None, item_value, rule_id
        ))

        conn.commit()
        cursor.close()
        conn.close()

        return JsonResponse({'success': True, 'status': status})

    except Exception as e:
        if conn:
            try:
                conn.rollback()
                conn.close()
            except Exception:
                pass
        return safe_error(e)
