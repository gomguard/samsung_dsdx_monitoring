"""
DX 데이터 관리 API
- 아이템 마스터 조회/저장
"""

import json
from datetime import datetime
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from apps.common.db import get_dx_connection


ALLOWED_TABLES = {'tv': 'tv_item_mst', 'hhp': 'hhp_item_mst'}


def _log_history(cursor, table_name, item_id, field_name, old_value, new_value, changed_id):
    """변경 이력 기록 (앱 서버 시간 기준)"""
    now = datetime.now()
    cursor.execute("""
        INSERT INTO item_mst_history (table_name, item_id, field_name, old_value, new_value, changed_id, changed_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """, (table_name, item_id, field_name, str(old_value), str(new_value), changed_id, now))


def item_master_list(request):
    """아이템 마스터 목록 조회"""
    table_key = request.GET.get('table', 'tv')
    table_name = ALLOWED_TABLES.get(table_key)
    if not table_name:
        return JsonResponse({'error': '잘못된 테이블'}, status=400)

    is_product = request.GET.get('is_product', '')
    account_name = request.GET.get('account_name', '')
    search = request.GET.get('search', '')
    search_field = request.GET.get('search_field', 'item')
    page = int(request.GET.get('page', 1))
    page_size = int(request.GET.get('page_size', 50))

    # 검색 필드 화이트리스트
    allowed_search_fields = {'item', 'sku', 'product_url'}
    if search_field not in allowed_search_fields:
        search_field = 'item'

    try:
        conn = get_dx_connection()
        cursor = conn.cursor()

        # WHERE 조건 구성
        conditions = []
        params = []

        if is_product == 'true':
            conditions.append('is_product = true')
        elif is_product == 'false':
            conditions.append('is_product = false')

        if account_name:
            conditions.append('account_name = %s')
            params.append(account_name)

        if search:
            if search.strip().lower() == 'null':
                # NULL이거나 빈 문자열인 항목 조회
                conditions.append(f'({search_field} IS NULL OR TRIM({search_field}) = \'\')')
            elif ',' in search:
                # 콤마가 포함되면 IN절로 정확 매칭
                keywords = [kw.strip() for kw in search.split(',') if kw.strip()]
                if keywords:
                    placeholders = ','.join(['%s'] * len(keywords))
                    conditions.append(f'{search_field} IN ({placeholders})')
                    params.extend(keywords)
            else:
                conditions.append(f'{search_field} ILIKE %s')
                params.append(f'%{search}%')

        where_clause = ''
        if conditions:
            where_clause = 'WHERE ' + ' AND '.join(conditions)

        # 통계 조회
        cursor.execute(f'SELECT COUNT(*) FROM {table_name}')
        total_all = cursor.fetchone()[0]

        cursor.execute(f'SELECT COUNT(*) FROM {table_name} WHERE is_product = true')
        total_product = cursor.fetchone()[0]

        total_non_product = total_all - total_product

        # 필터된 총 건수
        cursor.execute(f'SELECT COUNT(*) FROM {table_name} {where_clause}', params)
        total_filtered = cursor.fetchone()[0]

        # 특정 컬럼 (TV: screen_size, HHP: hhp_storage)
        extra_col = 'screen_size' if table_key == 'tv' else 'hhp_storage'

        # 데이터 조회
        offset = (page - 1) * page_size
        cursor.execute(f"""
            SELECT id, item, account_name, sku, {extra_col}, is_product, product_url
            FROM {table_name}
            {where_clause}
            ORDER BY account_name, item
            LIMIT %s OFFSET %s
        """, params + [page_size, offset])

        columns = ['id', 'item', 'account_name', 'sku', 'extra_col', 'is_product', 'product_url']
        items = []
        for row in cursor.fetchall():
            items.append(dict(zip(columns, row)))

        cursor.close()
        conn.close()

        return JsonResponse({
            'items': items,
            'total': total_filtered,
            'page': page,
            'page_size': page_size,
            'stats': {
                'total': total_all,
                'product': total_product,
                'non_product': total_non_product,
            },
            'extra_col_name': extra_col,
        })

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@require_POST
def item_master_save(request):
    """변경된 항목 일괄 저장 (각 항목별 개별 is_product 값)"""
    try:
        data = json.loads(request.body)
        table_key = data.get('table', 'tv')
        table_name = ALLOWED_TABLES.get(table_key)
        if not table_name:
            return JsonResponse({'error': '잘못된 테이블'}, status=400)

        changes = data.get('changes', [])
        user_id = data.get('user_id', '')

        if not changes:
            return JsonResponse({'error': '변경 항목 없음'}, status=400)

        conn = get_dx_connection()
        cursor = conn.cursor()

        # 현재 값 일괄 조회
        ids = [c['id'] for c in changes]
        placeholders = ','.join(['%s'] * len(ids))
        cursor.execute(
            f'SELECT id, is_product FROM {table_name} WHERE id IN ({placeholders})',
            ids
        )
        old_values = {row[0]: row[1] for row in cursor.fetchall()}

        # 건별 업데이트 + 이력 기록
        now = datetime.now()
        updated = 0
        for change in changes:
            item_id = change['id']
            new_val = change['is_product']
            old_val = old_values.get(item_id)

            if old_val is not None and old_val != new_val:
                cursor.execute(
                    f'UPDATE {table_name} SET is_product = %s, updated_at = %s WHERE id = %s',
                    (new_val, now, item_id)
                )
                _log_history(cursor, table_name, item_id, 'is_product', old_val, new_val, user_id)
                updated += 1

        conn.commit()
        cursor.close()
        conn.close()

        return JsonResponse({'success': True, 'updated': updated})

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
