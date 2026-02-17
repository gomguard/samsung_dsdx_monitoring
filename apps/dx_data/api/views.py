"""
DX 데이터 관리 API
- 아이템 마스터 조회/저장
- 변경 이력 조회
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
    try:
        page = max(1, int(request.GET.get('page', 1)))
        page_size = min(int(request.GET.get('page_size', 50)), 200)
    except (ValueError, TypeError):
        return JsonResponse({'error': '잘못된 페이지 파라미터'}, status=400)

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
        print(f'[ERROR] item_master_list: {e}')
        return JsonResponse({'error': '서버 오류가 발생했습니다.'}, status=500)


@require_POST
def item_master_save(request):
    """변경된 항목 일괄 저장 (is_product, is_checked 등)"""
    ALLOWED_FIELDS = {'is_product', 'is_checked'}
    try:
        data = json.loads(request.body)
        table_key = data.get('table', 'tv')
        table_name = ALLOWED_TABLES.get(table_key)
        if not table_name:
            return JsonResponse({'error': '잘못된 테이블'}, status=400)

        changes = data.get('changes', [])
        user_id = request.user.username if request.user.is_authenticated else ''

        if not changes:
            return JsonResponse({'error': '변경 항목 없음'}, status=400)

        conn = get_dx_connection()
        cursor = conn.cursor()

        # 현재 값 일괄 조회
        ids = [c['id'] for c in changes]
        placeholders = ','.join(['%s'] * len(ids))
        cursor.execute(
            f'SELECT id, is_product, is_checked FROM {table_name} WHERE id IN ({placeholders})',
            ids
        )
        old_values = {row[0]: {'is_product': row[1], 'is_checked': row[2]} for row in cursor.fetchall()}

        # 건별 업데이트 + 이력 기록
        now = datetime.now()
        updated = 0
        for change in changes:
            item_id = change['id']
            old_row = old_values.get(item_id)
            if not old_row:
                continue

            for field in ALLOWED_FIELDS:
                if field not in change:
                    continue
                new_val = change[field]
                old_val = old_row.get(field)
                if old_val is not None and old_val != new_val:
                    cursor.execute(
                        f'UPDATE {table_name} SET {field} = %s, updated_at = %s WHERE id = %s',
                        (new_val, now, item_id)
                    )
                    _log_history(cursor, table_name, item_id, field, old_val, new_val, user_id)
                    updated += 1

        conn.commit()
        cursor.close()
        conn.close()

        return JsonResponse({'success': True, 'updated': updated})

    except Exception as e:
        print(f'[ERROR] item_master_save: {e}')
        return JsonResponse({'error': '서버 오류가 발생했습니다.'}, status=500)


def item_master_history(request):
    """변경 이력 조회"""
    table_key = request.GET.get('table', 'tv')
    table_name = ALLOWED_TABLES.get(table_key)
    if not table_name:
        return JsonResponse({'error': '잘못된 테이블'}, status=400)

    date = request.GET.get('date', '')
    field = request.GET.get('field', '')
    account_name = request.GET.get('account_name', '')
    try:
        page = max(1, int(request.GET.get('page', 1)))
        page_size = min(int(request.GET.get('page_size', 50)), 200)
    except (ValueError, TypeError):
        return JsonResponse({'error': '잘못된 페이지 파라미터'}, status=400)

    allowed_fields = {'is_product', 'is_checked'}

    try:
        conn = get_dx_connection()
        cursor = conn.cursor()

        conditions = ['h.table_name = %s']
        params = [table_name]

        if date:
            conditions.append('h.changed_at::date = %s')
            params.append(date)

        if field and field in allowed_fields:
            conditions.append('h.field_name = %s')
            params.append(field)

        if account_name:
            conditions.append('m.account_name = %s')
            params.append(account_name)

        where = ' AND '.join(conditions)

        # 총 건수
        cursor.execute(f"""
            SELECT COUNT(*) FROM item_mst_history h
            LEFT JOIN {table_name} m ON m.id = h.item_id
            WHERE {where}
        """, params)
        total = cursor.fetchone()[0]

        # 데이터 조회 (item 정보 JOIN)
        offset = (page - 1) * page_size
        cursor.execute(f"""
            SELECT h.id, h.item_id, h.field_name, h.old_value, h.new_value,
                   h.changed_id, h.changed_at, m.item, m.account_name
            FROM item_mst_history h
            LEFT JOIN {table_name} m ON m.id = h.item_id
            WHERE {where}
            ORDER BY h.changed_at DESC
            LIMIT %s OFFSET %s
        """, params + [page_size, offset])

        items = []
        for row in cursor.fetchall():
            items.append({
                'id': row[0],
                'item_id': row[1],
                'field_name': row[2],
                'old_value': row[3],
                'new_value': row[4],
                'changed_id': row[5],
                'changed_at': row[6].strftime('%Y-%m-%d %H:%M:%S') if row[6] else '',
                'item': row[7] or '',
                'account_name': row[8] or '',
            })

        # 리테일러별 고유 item 목록 (전체 필터 기준, 페이지네이션 무관)
        cursor.execute(f"""
            SELECT DISTINCT m.account_name, m.item
            FROM item_mst_history h
            LEFT JOIN {table_name} m ON m.id = h.item_id
            WHERE {where}
            ORDER BY m.account_name, m.item
        """, params)
        unique_by_retailer = {}
        for row in cursor.fetchall():
            acc = row[0] or ''
            itm = row[1] or ''
            if itm:
                unique_by_retailer.setdefault(acc, []).append(itm)

        cursor.close()
        conn.close()

        return JsonResponse({
            'items': items,
            'total': total,
            'page': page,
            'page_size': page_size,
            'unique_items': unique_by_retailer,
        })

    except Exception as e:
        print(f'[ERROR] item_master_history: {e}')
        return JsonResponse({'error': '서버 오류가 발생했습니다.'}, status=500)
