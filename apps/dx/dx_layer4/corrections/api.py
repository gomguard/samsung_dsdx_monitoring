"""
Layer 4 검수기록 API — 목록 조회, 취소, 이유 조회, 이력 조회
"""

import json
from datetime import datetime, timedelta
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from apps.common.db import get_dx_connection
from apps.common.response import safe_error
from apps.common.params import parse_date
from apps.common.retail_columns import get_retailer_columns


# 원본 테이블별 수집 시간 컬럼 매핑
_CRAWL_TIME_COLUMN = {
    'tv_retail_com': 'crawl_datetime',
    'hhp_retail_com': 'crawl_strdatetime',
    'youtube_videos': 'created_at',
    'youtube_collection_logs': 'started_at',
    'youtube_comments': 'created_at',
    'market_trend': 'crawl_at_local_time',
    'market_comp_product': 'created_at',
    'market_comp_event': 'created_at',
    'openai_forecast_results': 'crawled_at',
}

# SQL 인젝션 방지: 허용된 테이블명만 사용
_ALLOWED_TABLES = set(_CRAWL_TIME_COLUMN.keys())


def _enrich_crawl_time(cursor, items):
    """items에 crawl_time 필드를 추가 (원본 테이블에서 수집 시간 조회)"""
    # table_name별로 record_id 그룹핑
    ids_by_table = {}
    for item in items:
        tn = item.get('table_name')
        rid = item.get('record_id')
        if tn and rid and tn in _ALLOWED_TABLES:
            ids_by_table.setdefault(tn, set()).add(rid)

    # 테이블별 수집 시간 조회
    crawl_time_map = {}  # (table_name, record_id) → crawl_time
    for tn, record_ids in ids_by_table.items():
        col = _CRAWL_TIME_COLUMN[tn]
        placeholders = ','.join(['%s'] * len(record_ids))
        cursor.execute(
            f"SELECT id, {col} FROM {tn} WHERE id IN ({placeholders})",
            list(record_ids)
        )
        for row in cursor.fetchall():
            if row[1]:
                crawl_time_map[(tn, row[0])] = row[1].strftime('%Y-%m-%d %H:%M') if hasattr(row[1], 'strftime') else str(row[1])

    # items에 crawl_time 추가
    for item in items:
        key = (item.get('table_name'), item.get('record_id'))
        item['crawl_time'] = crawl_time_map.get(key, '')


def corrections_list(request):
    """검수기록 목록 조회 (GET)"""
    target_date = parse_date(request.GET.get('date'))
    if target_date is None:
        return JsonResponse({'error': '날짜 형식이 올바르지 않습니다.'}, status=400)

    correction_type = request.GET.get('type', 'all')
    status = request.GET.get('status', 'all')
    search_field = request.GET.get('search_field', '')
    search_value = request.GET.get('search_value', '').strip()
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

        _SEARCH_FIELDS = {
            'category': 'c.table_name',
            'retailer': 'c.retailer',
            'column_name': 'c.column_name',
            'item': 'c.item',
            'record_id': None,
            'correction_type': 'c.correction_type',
        }
        if search_value and search_field in _SEARCH_FIELDS:
            if search_field == 'record_id':
                base_clauses.append("CAST(c.record_id AS TEXT) LIKE %s")
                base_params.append(f'%{search_value}%')
            else:
                col = _SEARCH_FIELDS[search_field]
                base_clauses.append(f"{col} ILIKE %s")
                base_params.append(f'%{search_value}%')

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

        # 수집 시간 조회 (record_id → 원본 테이블 crawl_time)
        _enrich_crawl_time(cursor, items)

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


# 이력 조회: 허용 테이블 → (product_line, date_column)
_HISTORY_TABLES = {
    'tv_retail_com': ('tv', 'crawl_datetime'),
    'hhp_retail_com': ('hhp', 'crawl_strdatetime'),
}


def corrections_history(request):
    """원본 테이블 이력 조회 API (GET) — retailer+item 기준 최근 N일"""
    table_name = request.GET.get('table_name', '')
    retailer = request.GET.get('retailer', '')
    item = request.GET.get('item', '')
    column = request.GET.get('column', '')
    days = int(request.GET.get('days', 3))
    record_id = request.GET.get('record_id', '')

    if table_name not in _HISTORY_TABLES:
        return JsonResponse({'success': False, 'error': '지원하지 않는 테이블입니다.'}, status=400)
    if not retailer or not item:
        return JsonResponse({'success': False, 'error': 'retailer, item은 필수입니다.'}, status=400)

    product_line, date_col = _HISTORY_TABLES[table_name]

    # monitoring_retail_columns에서 컬럼 목록 조회
    retail_columns = get_retailer_columns(product_line, retailer)
    if not retail_columns:
        return JsonResponse({'success': False, 'error': '컬럼 정보를 찾을 수 없습니다.'}, status=400)

    # id, date_col, item은 항상 포함 (고정 컬럼)
    fixed_cols = ['id', date_col, 'item']
    other_cols = [c for c in retail_columns if c not in fixed_cols and c != 'product_url']
    select_cols = fixed_cols + other_cols
    # product_url이 있으면 마지막 열에 고정 배치
    has_product_url = 'product_url' in retail_columns
    if has_product_url:
        select_cols.append('product_url')
    select_sql = ', '.join(select_cols)

    # 초기 표시 컬럼: 고정 컬럼 + 수정된 컬럼 + product_url
    default_visible = ['id', date_col, 'item']
    if column and column in retail_columns and column not in default_visible:
        default_visible.append(column)
    if has_product_url:
        default_visible.append('product_url')

    conn = None
    try:
        conn = get_dx_connection()
        cursor = conn.cursor()

        since_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
        cursor.execute(
            f"SELECT {select_sql} FROM {table_name} "
            f"WHERE account_name = %s AND item = %s AND ({date_col})::date >= %s::date "
            f"ORDER BY {date_col} ASC",
            (retailer, item, since_date)
        )

        col_names = [desc[0] for desc in cursor.description]
        rows = []
        for row in cursor.fetchall():
            item_dict = {}
            for i, val in enumerate(row):
                if hasattr(val, 'strftime'):
                    item_dict[col_names[i]] = val.strftime('%Y-%m-%d %H:%M:%S')
                elif val is None:
                    item_dict[col_names[i]] = ''
                else:
                    item_dict[col_names[i]] = str(val)
            rows.append(item_dict)

        cursor.close()
        conn.close()

        # 프론트에 보낼 컬럼 목록
        columns = list(select_cols)
        # 고정 컬럼
        fixed = list(fixed_cols)

        return JsonResponse({
            'success': True,
            'columns': columns,
            'fixed': fixed,
            'default_visible': default_visible,
            'record_id': int(record_id) if record_id else None,
            'rows': rows,
        })
    except Exception as e:
        if conn:
            try:
                conn.close()
            except Exception:
                pass
        return safe_error(e)
