"""
Macro Repositories: 테이블 기반 수집 건수 및 원본 데이터 조회
"""


def get_macro_collection_count(cursor, table_name, target_date_str):
    """특정 테이블의 수집 건수 조회 (운영 테이블 직접 참조)"""
    cursor.execute(f"""
        SELECT COUNT(*) FROM {table_name}
        WHERE created_at::date = %s
    """, [target_date_str])
    return cursor.fetchone()[0]


def get_macro_raw_data(cursor, table_name, target_date_str):
    """특정 테이블의 원본 데이터 조회 (최대 500건)"""
    cursor.execute(f"""
        SELECT * FROM {table_name}
        WHERE created_at::date = %s
        ORDER BY created_at DESC
        LIMIT 500
    """, [target_date_str])
    columns = [desc[0] for desc in cursor.description]
    rows = []
    for row in cursor.fetchall():
        rows.append([str(v) if v is not None else '' for v in row])
    return columns, rows
