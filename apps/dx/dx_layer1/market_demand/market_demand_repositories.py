"""
DX Layer 1 Market Demand Repositories: 데이터베이스 I/O 쿼리 전담 계층
"""
from decimal import Decimal

def get_nine_weeks_later_keywords_count(cursor, query_date, nine_weeks_later):
    """9주 이내 키워드 통계 (카테고리별) - 오늘 제외"""
    cursor.execute("""
        SELECT k.category, COUNT(*) as cnt
        FROM openai_keywords k
        JOIN openai_event_mst e ON k.event_name = e.event_name
        WHERE e.is_active = true
        AND e.event_date > %s AND e.event_date <= %s
        GROUP BY k.category
    """, (query_date, nine_weeks_later))
    return {row[0]: row[1] for row in cursor.fetchall()}


def get_one_week_later_keywords_count(cursor, query_date, one_week_later):
    """1주 이내 키워드 통계 (제외 대상, 카테고리별)"""
    cursor.execute("""
        SELECT k.category, COUNT(*) as cnt
        FROM openai_keywords k
        JOIN openai_event_mst e ON k.event_name = e.event_name
        WHERE e.is_active = true
        AND e.event_date >= %s AND e.event_date <= %s
        GROUP BY k.category
    """, (query_date, one_week_later))
    return {row[0]: row[1] for row in cursor.fetchall()}


def get_collected_keywords_count(cursor, query_date):
    """수집 결과 수 통계 (카테고리별)"""
    cursor.execute("""
        SELECT k.category, COUNT(*) as cnt
        FROM openai_forecast_results f
        JOIN openai_keywords k ON f.product_name = k.product_name
            AND REPLACE(UPPER(f.event), '_', ' ') = UPPER(k.event_name)
        WHERE f.crawled_at::date = %s
        GROUP BY k.category
    """, (query_date,))
    return {row[0]: row[1] for row in cursor.fetchall()}


def get_raw_data_list(cursor, target_date, category):
    """Market 수요증감율 Raw Data 조회"""
    columns = [
        'product_name', 'event', 'metric_type', 'event_offset',
        'event_value', 'comment', 'week', 'forecast_result', 'crawled_at'
    ]

    query = """
        SELECT
            f.product_name,
            f.event,
            f.metric_type,
            f.event_offset,
            f.event_value,
            f.comment,
            f.week,
            f.forecast_result,
            f.crawled_at
        FROM openai_forecast_results f
        JOIN openai_keywords k ON f.product_name = k.product_name
            AND REPLACE(UPPER(f.event), '_', ' ') = UPPER(k.event_name)
        WHERE f.crawled_at::date = %s
        AND k.category = %s
        ORDER BY f.crawled_at DESC
        LIMIT 500
    """
    cursor.execute(query, (target_date, category))
    rows = cursor.fetchall()
    
    processed = []
    for row in rows:
        processed.append(tuple(
            float(v) if isinstance(v, Decimal) else v
            for v in row
        ))

    return columns, processed


def get_target_keywords_list(cursor, target_date, nine_weeks_later, category):
    """대상 키워드 조회 (9주 이내 이벤트)"""
    target_query = """
        SELECT k.category, k.product_name, k.event_name, e.event_date
        FROM openai_keywords k
        JOIN openai_event_mst e ON k.event_name = e.event_name
        WHERE e.is_active = true
        AND e.event_date > %s AND e.event_date <= %s
        {category_filter}
        ORDER BY k.category, e.event_date, k.product_name
    """
    if category != 'all':
        target_query = target_query.format(category_filter=f"AND k.category = '{category}'")
    else:
        target_query = target_query.format(category_filter="")

    cursor.execute(target_query, (target_date, nine_weeks_later))
    return cursor.fetchall()


def get_collected_events_set(cursor, target_date, category):
    """수집된 키워드 조회"""
    collected_query = """
        SELECT DISTINCT k.category, f.product_name,
               REPLACE(UPPER(f.event), '_', ' ') as event_name
        FROM openai_forecast_results f
        JOIN openai_keywords k ON f.product_name = k.product_name
            AND REPLACE(UPPER(f.event), '_', ' ') = UPPER(k.event_name)
        WHERE f.crawled_at::date = %s
        {category_filter}
    """
    if category != 'all':
        collected_query = collected_query.format(category_filter=f"AND k.category = '{category}'")
    else:
        collected_query = collected_query.format(category_filter="")

    cursor.execute(collected_query, (target_date,))
    collected_set = set()
    for row in cursor.fetchall():
        collected_set.add((row[0], row[1], row[2].upper()))
    return collected_set
