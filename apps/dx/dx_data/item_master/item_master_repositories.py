"""
DX Data Item Master Repositories - 데이터베이스 I/O
"""

def insert_item_mst_history_db(cursor, table_name, item_id, field_name, old_value, new_value, changed_id, now):
    """변경 이력 기록"""
    cursor.execute(f"""
        INSERT INTO item_mst_history (table_name, item_id, field_name, old_value, new_value, changed_id, changed_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """, (table_name, item_id, field_name, str(old_value), str(new_value), changed_id, now))


def get_item_master_counts_db(cursor, table_name, where_clause, params):
    """검색 조건에 맞는 전체 카운트 조회"""
    cursor.execute(f'SELECT COUNT(*) FROM {table_name} {where_clause}', params)
    return cursor.fetchone()[0]


def get_item_master_page_db(cursor, table_name, where_clause, params, extra_col, page_size, offset):
    """페이징된 아이템 마스터 데이터 조회"""
    cursor.execute(f"""
        SELECT id, item, account_name, sku, {extra_col}, is_product, is_checked, product_url
        FROM {table_name}
        {where_clause}
        ORDER BY account_name, item
        LIMIT %s OFFSET %s
    """, params + [page_size, offset])
    columns = ['id', 'item', 'account_name', 'sku', 'extra_col', 'is_product', 'is_checked', 'product_url']
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def get_items_by_ids_db(cursor, table_name, ids):
    """지정된 ID들의 현재 데이터 조회"""
    if not ids:
        return {}
    placeholders = ','.join(['%s'] * len(ids))
    cursor.execute(f'SELECT id, is_product, is_checked FROM {table_name} WHERE id IN ({placeholders})', ids)
    return {row[0]: {'is_product': row[1], 'is_checked': row[2]} for row in cursor.fetchall()}


def update_item_field_db(cursor, table_name, field, new_val, now, item_id):
    """아이템 필드 단건 수정"""
    cursor.execute(
        f'UPDATE {table_name} SET {field} = %s, updated_at = %s WHERE id = %s',
        (new_val, now, item_id)
    )


def get_history_counts_db(cursor, table_name, where, params):
    """이력 전체 카운트 조회"""
    cursor.execute(f"""
        SELECT COUNT(*) FROM item_mst_history h
        LEFT JOIN {table_name} m ON m.id = h.item_id
        WHERE {where}
    """, params)
    return cursor.fetchone()[0]


def get_history_page_db(cursor, table_name, where, params, page_size, offset):
    """이력 데이터 페이징 조회"""
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
    return items


def get_history_unique_retailers_db(cursor, table_name, where, params):
    """이력 기반 unique 리테일러 항목 조회"""
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
    return unique_by_retailer
