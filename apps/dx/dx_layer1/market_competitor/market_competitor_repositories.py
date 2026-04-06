"""
DX Layer 1 Market Competitor Repositories: 데이터베이스 I/O 쿼리 전담 계층
"""

def get_comp_product_collected_count(cursor, comp_batch_id):
    """카테고리별 수집수 조회"""
    if not comp_batch_id:
        return {}
    cursor.execute("""
        SELECT
            COALESCE(category, 'Unknown') as category,
            COUNT(*) as collected_count
        FROM market_comp_product
        WHERE batch_id = %s
        GROUP BY category
        ORDER BY category
    """, (comp_batch_id,))
    return {row[0]: row[1] for row in cursor.fetchall()}


def get_mst_count_by_type(cursor, analysis_type, content_type):
    """지정된 타입 조건의 키워드 개수 반환 (product_line별)"""
    cursor.execute("""
        SELECT
            product_line,
            COUNT(*) as cnt
        FROM market_mst
        WHERE analysis_type = %s AND content_type = %s AND is_active = true
        GROUP BY product_line
    """, (analysis_type, content_type))
    return {row[0]: row[1] for row in cursor.fetchall()}


def get_mst_keywords_by_type(cursor, analysis_type, content_type):
    """지정된 타입 조건의 키워드 목록 조회 (product_line별)"""
    cursor.execute("""
        SELECT product_line, keyword
        FROM market_mst
        WHERE analysis_type = %s AND content_type = %s AND is_active = true
        ORDER BY product_line, keyword
    """, (analysis_type, content_type))
    
    result = {}
    for row in cursor.fetchall():
        pl = row[0]
        if pl not in result:
            result[pl] = []
        result[pl].append(row[1])
    return result


def get_mst_keywords_by_category_and_type(cursor, analysis_type, content_type, category):
    """특정 카테고리와 타입의 키워드 목록 조회"""
    cursor.execute("""
        SELECT keyword
        FROM market_mst
        WHERE analysis_type = %s AND content_type = %s AND is_active = true AND product_line = %s
    """, (analysis_type, content_type, category))
    return [r[0] for r in cursor.fetchall()]


def get_comp_product_combinations(cursor, comp_batch_id):
    """조합(samsung_series_name, comp_brand) 목록 조회 (product_line별)"""
    result = {}
    if comp_batch_id:
        cursor.execute("""
            SELECT
                category,
                samsung_series_name,
                comp_brand
            FROM market_comp_product
            WHERE batch_id = %s
            GROUP BY category, samsung_series_name, comp_brand
        """, (comp_batch_id,))
        for row in cursor.fetchall():
            pl = row[0]
            if pl not in result:
                result[pl] = set()
            result[pl].add((row[1], row[2]))
    return result


def get_comp_product_combinations_by_category(cursor, comp_batch_id, category):
    """특정 카테고리의 조합(samsung_series_name, comp_brand) 목록 조회"""
    collected_combos = set()
    if comp_batch_id:
        cursor.execute("""
            SELECT samsung_series_name, comp_brand
            FROM market_comp_product
            WHERE batch_id = %s AND category = %s
            GROUP BY samsung_series_name, comp_brand
        """, (comp_batch_id, category))
        for row in cursor.fetchall():
            collected_combos.add((row[0], row[1]))
    return collected_combos


def get_competitor_keywords_list(cursor, category):
    """키워드 등록 현황 조회"""
    columns = ['id', 'product_line', 'content_type', 'keyword', 'is_active', 'created_at']
    query = """
        SELECT id, product_line, content_type, keyword, is_active, created_at
        FROM market_mst
        WHERE analysis_type = 'competitor'
    """
    params = []

    if category:
        query += " AND product_line = %s"
        params.append(category)

    query += " ORDER BY product_line, content_type, keyword"

    cursor.execute(query, params)
    data = []
    for row in cursor.fetchall():
        row_list = list(row)
        for i, val in enumerate(row_list):
            if hasattr(val, 'strftime'):
                row_list[i] = val.strftime('%Y-%m-%d %H:%M:%S')
        data.append(row_list)
    return columns, data


def get_competitor_raw_data_list(cursor, comp_batch_id, category):
    """Raw Data (market_comp_product) 조회"""
    columns = [
        'id', 'category', 'samsung_series_name', 'comp_brand', 'comp_series_name',
        'expected_release', 'release_status', 'comment', 'calender_week', 'created_at'
    ]
    query = """
        SELECT id, category, samsung_series_name, comp_brand, comp_series_name,
               expected_release, release_status, comment, calender_week, created_at
        FROM market_comp_product
        WHERE batch_id = %s
    """
    params = [comp_batch_id]

    if category:
        query += " AND category = %s"
        params.append(category)

    query += " ORDER BY category, samsung_series_name, comp_brand"

    cursor.execute(query, params)
    data = []
    for row in cursor.fetchall():
        row_list = list(row)
        for i, val in enumerate(row_list):
            if hasattr(val, 'strftime'):
                row_list[i] = val.strftime('%Y-%m-%d %H:%M:%S')
        data.append(row_list)
    return columns, data
