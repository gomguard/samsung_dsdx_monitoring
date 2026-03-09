"""
Layer 4 검수기록 API — 목록 조회, 취소, 이유 조회
"""

import json
from datetime import datetime
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from apps.common.db import get_dx_connection
from apps.common.response import safe_error
from apps.common.params import parse_date


def corrections_list(request):
    """검수기록 목록 조회 (GET)"""
    target_date = parse_date(request.GET.get('date'))
    if target_date is None:
        return JsonResponse({'error': '날짜 형식이 올바르지 않습니다.'}, status=400)

    correction_type = request.GET.get('type', 'all')
    status = request.GET.get('status', 'all')
    category = request.GET.get('category', 'all')
    rule_name = request.GET.get('rule_name', 'all')
    page = int(request.GET.get('page', 1))
    page_size = int(request.GET.get('page_size', 50))

    conn = None
    try:
        conn = get_dx_connection()
        cursor = conn.cursor()

        base_clauses = ["c.crawl_date = %s", "c.status IS NOT NULL"]
        base_params = [str(target_date)]

        if correction_type != 'all':
            base_clauses.append("c.correction_type = %s")
            base_params.append(correction_type)

        if category != 'all':
            category_table_map = {'TV': 'tv_retail_com', 'HHP': 'hhp_retail_com'}
            table_name = category_table_map.get(category)
            if table_name:
                base_clauses.append("c.table_name = %s")
                base_params.append(table_name)

        if rule_name != 'all':
            base_clauses.append("c.rule_id IN (SELECT id FROM monitoring_validation_rules WHERE detail_name = %s)")
            base_params.append(rule_name)

        # 탭 카운트 (status 필터 제외)
        base_where_sql = " AND ".join(base_clauses)
        cursor.execute(f"""
            SELECT c.status, COUNT(*) FROM monitoring_corrections c
            WHERE {base_where_sql}
            GROUP BY c.status
        """, base_params)
        status_counts = {}
        for row in cursor.fetchall():
            status_counts[row[0]] = row[1]

        # status 필터 적용
        where_clauses = list(base_clauses)
        params = list(base_params)
        if status != 'all':
            where_clauses.append("c.status = %s")
            params.append(status)

        where_sql = " AND ".join(where_clauses)

        # 총 건수
        cursor.execute(f"SELECT COUNT(*) FROM monitoring_corrections c WHERE {where_sql}", params)
        total_count = cursor.fetchone()[0]

        # 데이터 조회
        offset = (page - 1) * page_size
        cursor.execute(f"""
            SELECT c.id, c.layer, c.correction_type, c.table_name, c.record_id,
                   c.column_name, c.old_value, c.new_value, c.crawl_date,
                   c.status, c.memo, c.created_id, c.created_at, c.reason,
                   c.retailer, c.item, c.rule_id, r.detail_name,
                   c.updated_id, c.updated_at, c.cancel_memo
            FROM monitoring_corrections c
            LEFT JOIN monitoring_validation_rules r ON c.rule_id = r.id
            WHERE {where_sql}
            ORDER BY c.created_at DESC
            LIMIT %s OFFSET %s
        """, params + [page_size, offset])

        rows = cursor.fetchall()
        items = []
        for row in rows:
            items.append({
                'id': row[0],
                'layer': row[1],
                'correction_type': row[2],
                'table_name': row[3],
                'record_id': row[4],
                'column_name': row[5],
                'old_value': row[6],
                'new_value': row[7],
                'crawl_date': str(row[8]) if row[8] else '',
                'status': row[9],
                'memo': row[10] or '',
                'created_id': row[11] or '',
                'created_at': row[12].strftime('%Y-%m-%d %H:%M:%S') if row[12] else '',
                'reason': row[13] or '',
                'retailer': row[14] or '',
                'item': row[15] or '',
                'rule_id': row[16],
                'rule_name': row[17] or '',
                'updated_id': row[18] or '',
                'updated_at': row[19].strftime('%Y-%m-%d %H:%M:%S') if row[19] else '',
                'cancel_memo': row[20] or '',
            })

        # 크로스필드일 때 룰 목록 반환 (detail_name 기준 중복 제거)
        rule_options = []
        if correction_type == 'cross_field':
            cursor.execute("""
                SELECT DISTINCT r.detail_name
                FROM monitoring_corrections c
                LEFT JOIN monitoring_validation_rules r ON c.rule_id = r.id
                WHERE c.crawl_date = %s AND c.correction_type = 'cross_field'
                  AND c.status IS NOT NULL AND c.rule_id IS NOT NULL
                ORDER BY r.detail_name
            """, [str(target_date)])
            for rrow in cursor.fetchall():
                if rrow[0]:
                    rule_options.append({'name': rrow[0]})

        cursor.close()
        conn.close()

        total_pages = (total_count + page_size - 1) // page_size

        resp = {
            'success': True,
            'items': items,
            'total': total_count,
            'page': page,
            'page_size': page_size,
            'total_pages': total_pages,
            'status_counts': {
                'corrected': status_counts.get('corrected', 0),
                'normal': status_counts.get('normal', 0),
                'reverted': status_counts.get('reverted', 0),
            },
        }
        if rule_options:
            resp['rule_options'] = rule_options

        return JsonResponse(resp)
    except Exception as e:
        if conn:
            try:
                conn.close()
            except Exception:
                pass
        return safe_error(e)


@require_POST
def corrections_cancel(request):
    """정상처리 일괄 취소 API"""
    try:
        data = json.loads(request.body)
        ids = data.get('ids', [])
        cancel_memo = data.get('cancel_memo', '')
        username = request.user.username if request.user.is_authenticated else ''
        now = datetime.now()

        if not ids or not isinstance(ids, list):
            return JsonResponse({'success': False, 'error': '취소할 항목을 선택하세요.'}, status=400)

        conn = get_dx_connection()
        cursor = conn.cursor()
        try:
            placeholders = ','.join(['%s'] * len(ids))
            cursor.execute(f"""
                UPDATE monitoring_corrections
                SET status = 'reverted', updated_id = %s, updated_at = %s, cancel_memo = %s
                WHERE id IN ({placeholders}) AND status = 'normal'
            """, [username, now, cancel_memo or None] + ids)
            cancelled = cursor.rowcount
            conn.commit()
            return JsonResponse({'success': True, 'cancelled': cancelled})
        finally:
            cursor.close()
            conn.close()
    except Exception as e:
        return safe_error(e, 'corrections_cancel')


def review_reasons(request):
    """정상 처리 이유 목록 조회 API (GET) — 코드 상수에서 반환"""
    from apps.common.constants import get_reasons
    check_type = request.GET.get('check_type', 'null_check')
    reasons = [{'text': r} for r in get_reasons(check_type)]
    return JsonResponse({'success': True, 'reasons': reasons})
