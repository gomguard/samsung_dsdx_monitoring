"""
DX 데이터 관리 Services — 아이템 마스터 조회/저장, 변경 이력
"""

from datetime import datetime
from apps.common.db import dx_connection
from .item_master_repositories import (
    insert_item_mst_history_db,
    get_item_master_counts_db,
    get_item_master_page_db,
    get_items_by_ids_db,
    update_item_field_db,
    get_history_counts_db,
    get_history_page_db,
    get_history_unique_retailers_db,
)

ALLOWED_TABLES = {'tv': 'tv_item_mst', 'hhp': 'hhp_item_mst'}
ALLOWED_FIELDS = {'is_product', 'is_checked'}
ALLOWED_SEARCH_FIELDS = {'item', 'sku', 'product_url'}


def _log_history(cursor, table_name, item_id, field_name, old_value, new_value, changed_id):
    """변경 이력 기록 (앱 서버 시간 기준)"""
    now = datetime.now()
    insert_item_mst_history_db(cursor, table_name, item_id, field_name, old_value, new_value, changed_id, now)


def _build_conditions(is_product, is_checked, account_name, search, search_field):
    """필터 조건 및 파라미터 구성"""
    conditions = []
    params = []

    if is_product == 'true':
        conditions.append('is_product = true')
    elif is_product == 'false':
        conditions.append('is_product = false')

    if is_checked == 'true':
        conditions.append('is_checked = true')
    elif is_checked == 'false':
        conditions.append('is_checked = false')

    if account_name:
        conditions.append('account_name = %s')
        params.append(account_name)

    if search:
        if search.strip().lower() == 'null':
            conditions.append(f'({search_field} IS NULL OR TRIM({search_field}) = \'\')')
        elif ',' in search:
            keywords = [kw.strip() for kw in search.split(',') if kw.strip()]
            if keywords:
                placeholders = ','.join(['%s'] * len(keywords))
                conditions.append(f'{search_field} IN ({placeholders})')
                params.extend(keywords)
        else:
            conditions.append(f'{search_field} ILIKE %s')
            params.append(f'%{search}%')

    return conditions, params


def get_item_master_list(table_key, is_product, is_checked, account_name, search, search_field, page, page_size):
    """아이템 마스터 목록 조회"""
    table_name = ALLOWED_TABLES[table_key]

    if search_field not in ALLOWED_SEARCH_FIELDS:
        search_field = 'item'

    conditions, params = _build_conditions(is_product, is_checked, account_name, search, search_field)
    where_clause = ''
    if conditions:
        where_clause = 'WHERE ' + ' AND '.join(conditions)

    extra_col = 'screen_size' if table_key == 'tv' else 'hhp_storage'

    with dx_connection() as (conn, cursor):
        total_filtered = get_item_master_counts_db(cursor, table_name, where_clause, params)

        offset = (page - 1) * page_size
        items = get_item_master_page_db(cursor, table_name, where_clause, params, extra_col, page_size, offset)

    return {
        'items': items,
        'total': total_filtered,
        'page': page,
        'page_size': page_size,
        'extra_col_name': extra_col,
    }


def save_item_master(table_key, changes, user_id):
    """변경된 항목 일괄 저장 (is_product, is_checked)"""
    table_name = ALLOWED_TABLES[table_key]

    with dx_connection() as (conn, cursor):
        ids = [c['id'] for c in changes]
        old_values = get_items_by_ids_db(cursor, table_name, ids)

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
                    update_item_field_db(cursor, table_name, field, new_val, now, item_id)
                    _log_history(cursor, table_name, item_id, field, old_val, new_val, user_id)
                    updated += 1

        conn.commit()

    return updated


def get_item_master_history(table_key, date, field, account_name, item_search, page, page_size):
    """변경 이력 조회"""
    table_name = ALLOWED_TABLES[table_key]
    allowed_fields = {'is_product', 'is_checked'}

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

    if item_search:
        conditions.append('m.item ILIKE %s')
        params.append(f'%{item_search}%')

    where = ' AND '.join(conditions)

    with dx_connection() as (conn, cursor):
        total = get_history_counts_db(cursor, table_name, where, params)

        offset = (page - 1) * page_size
        items = get_history_page_db(cursor, table_name, where, params, page_size, offset)

        unique_by_retailer = get_history_unique_retailers_db(cursor, table_name, where, params)

    return {
        'items': items,
        'total': total,
        'page': page,
        'page_size': page_size,
        'unique_items': unique_by_retailer,
    }
