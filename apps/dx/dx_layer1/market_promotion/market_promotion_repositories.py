"""
DX Layer 1 Market Promotion Repositories: 데이터베이스 I/O 쿼리 전담 계층
"""

def get_event_count_within_weeks(cursor, target_date_str, limit_date_str):
    """지정 기간 내 활성 이벤트 수 조회"""
    cursor.execute("""
        SELECT COUNT(DISTINCT id)
        FROM openai_event_mst
        WHERE is_active = true
          AND event_date IS NOT NULL
          AND event_date > %s
          AND event_date <= %s
    """, (target_date_str, limit_date_str))
    return cursor.fetchone()[0] or 0


def get_collected_promotions_by_retailer(cursor, target_date_str):
    """해당 날짜에 수집된 프로모션 데이터 행 수 조회 (리테일러별)"""
    cursor.execute("""
        SELECT
            p.retailer,
            COUNT(*) as cnt
        FROM openai_retailer_promotions p
        WHERE p.crawled_at = %s
        GROUP BY p.retailer
        ORDER BY p.retailer
    """, (target_date_str,))
    return {row[0]: row[1] for row in cursor.fetchall()}


def get_promotion_raw_data_list(cursor, retailer, analysis_date_str):
    """프로모션 수집 결과 상세 데이터 목록 조회"""
    columns = [
        'id', 'event_name', 'event_date', 'event_week',
        'retailer', 'promo_start_date', 'promo_end_date',
        'source_url', 'crawled_at'
    ]

    query = """
        SELECT
            p.id,
            e.event_name,
            e.event_date,
            e.event_week,
            p.retailer,
            p.promo_start_date,
            p.promo_end_date,
            p.source_url,
            p.crawled_at
        FROM openai_retailer_promotions p
        LEFT JOIN openai_event_mst e ON p.event_id = e.id
        WHERE p.crawled_at = %s
    """

    params = [analysis_date_str]

    if retailer:
        query += " AND p.retailer = %s"
        params.append(retailer)

    query += " ORDER BY e.event_date, p.id"

    cursor.execute(query, params)
    rows = cursor.fetchall()

    return columns, rows
