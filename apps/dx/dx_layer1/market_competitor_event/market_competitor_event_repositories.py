"""
DX Layer 1 Market Competitor Event Repositories: 데이터베이스 I/O 쿼리 전담 계층
"""

def get_recent_event_batch_id(cursor, month_start, month_end):
    """해당 월에 실행된 최신 이벤트 배치 조회"""
    cursor.execute("""
        SELECT batch_id, MAX(created_at) as last_run
        FROM market_comp_event
        WHERE batch_id IS NOT NULL
          AND created_at >= %s AND created_at < %s::date + INTERVAL '1 day'
        GROUP BY batch_id
        ORDER BY last_run DESC
        LIMIT 1
    """, (month_start, month_end))
    return cursor.fetchone()


def get_event_collected_count(cursor, event_batch_id):
    """카테고리별 이벤트 분석 건수"""
    if not event_batch_id:
        return {}
    cursor.execute("""
        SELECT
            category,
            COUNT(*) as collected_count
        FROM market_comp_event
        WHERE batch_id = %s
        GROUP BY category
        ORDER BY category
    """, (event_batch_id,))
    return {row[0]: row[1] for row in cursor.fetchall()}


def get_expected_event_count(cursor, comp_batch_id):
    """기대건수: market_comp_product에서 comp_brand + comp_series_name 중복 제거 건수"""
    if not comp_batch_id:
        return {}
    cursor.execute("""
        SELECT
            category,
            COUNT(DISTINCT comp_brand || '||' || comp_series_name) as expected_count
        FROM market_comp_product
        WHERE batch_id = %s
          AND comp_series_name != 'info_not_available'
        GROUP BY category
        ORDER BY category
    """, (comp_batch_id,))
    return {row[0]: row[1] for row in cursor.fetchall()}


def get_expected_event_combos(cursor, comp_batch_id):
    """기대 조합 목록 (키워드 커버리지용)"""
    result = {}
    if comp_batch_id:
        cursor.execute("""
            SELECT
                category,
                comp_brand || '||' || comp_series_name as combo
            FROM market_comp_product
            WHERE batch_id = %s
              AND comp_series_name != 'info_not_available'
            GROUP BY category, comp_brand, comp_series_name
        """, (comp_batch_id,))
        for row in cursor.fetchall():
            cat = row[0]
            if cat not in result:
                result[cat] = set()
            result[cat].add(row[1])
    return result


def get_collected_event_combos(cursor, event_batch_id):
    """수집된 단말 조합 목록 (키워드 커버리지용)"""
    result = {}
    if event_batch_id:
        cursor.execute("""
            SELECT
                category,
                comp_brand || '||' || comp_sku_name as combo
            FROM market_comp_event
            WHERE batch_id = %s
            GROUP BY category, comp_brand, comp_sku_name
        """, (event_batch_id,))
        for row in cursor.fetchall():
            cat = row[0]
            if cat not in result:
                result[cat] = set()
            result[cat].add(row[1])
    return result


def get_expected_combos_by_category(cursor, comp_batch_id, category):
    """특정 카테고리의 기대 조합 목록"""
    result = set()
    if comp_batch_id:
        cursor.execute("""
            SELECT comp_brand, comp_series_name
            FROM market_comp_product
            WHERE batch_id = %s AND category = %s AND comp_series_name != 'info_not_available'
            GROUP BY comp_brand, comp_series_name
        """, (comp_batch_id, category))
        for row in cursor.fetchall():
            result.add((row[0], row[1]))
    return result


def get_collected_combos_by_category(cursor, event_batch_id, category):
    """특정 카테고리의 수집된 단말 조합 목록"""
    result = set()
    if event_batch_id:
        cursor.execute("""
            SELECT comp_brand, comp_sku_name
            FROM market_comp_event
            WHERE batch_id = %s AND category = %s
            GROUP BY comp_brand, comp_sku_name
        """, (event_batch_id, category))
        for row in cursor.fetchall():
            result.add((row[0], row[1]))
    return result


def get_competitor_event_raw_data_list(cursor, event_batch_id, category):
    """Market Competitor Event Raw Data 조회"""
    columns = [
        'id', 'category', 'comp_brand', 'comp_sku_name', 'comp_launch_date',
        'comp_preorder', 'comp_pre_order_start_date', 'comp_preorder_end_date',
        'rumor_release_window', 'rumor_preorder_window', 'rumor_confidence_level',
        'calender_week', 'created_at'
    ]
    query = """
        SELECT id, category, comp_brand, comp_sku_name, comp_launch_date,
               comp_preorder, comp_pre_order_start_date, comp_preorder_end_date,
               rumor_release_window, rumor_preorder_window, rumor_confidence_level,
               calender_week, created_at
        FROM market_comp_event
        WHERE batch_id = %s
    """
    params = [event_batch_id]

    if category:
        query += " AND category = %s"
        params.append(category)

    query += " ORDER BY category, comp_brand, comp_sku_name"

    cursor.execute(query, params)
    data = []
    for row in cursor.fetchall():
        row_list = list(row)
        for i, val in enumerate(row_list):
            if hasattr(val, 'strftime'):
                row_list[i] = val.strftime('%Y-%m-%d %H:%M:%S')
        data.append(row_list)
    return columns, data
