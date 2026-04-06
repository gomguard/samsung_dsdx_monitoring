"""
DX Layer 1 Market Trend Repositories: 데이터베이스 I/O 쿼리 전담 계층
"""

def get_market_expected_counts(cursor):
    """Market Trend 기대건수 (market_mst에서 product_line + content_type별 키워드 수)"""
    cursor.execute("""
        SELECT
            product_line,
            content_type,
            COUNT(*) as expected_count
        FROM market_mst
        WHERE analysis_type = 'trend'
        GROUP BY product_line, content_type
        ORDER BY product_line, content_type
    """)
    return {f"{row[0]}_{row[1]}": row[2] for row in cursor.fetchall()}


def get_market_collected_counts(cursor, target_date_str):
    """Market Trend 수집건수 (전일 데이터)"""
    cursor.execute("""
        SELECT
            m.product_line,
            m.content_type,
            COUNT(*) as collected_count
        FROM market_trend t
        INNER JOIN market_mst m ON m.analysis_type = 'trend' AND t.keyword = m.keyword
        WHERE DATE(t.crawl_at_local_time) = %s
        GROUP BY m.product_line, m.content_type
    """, (target_date_str,))
    return {f"{row[0]}_{row[1]}": row[2] for row in cursor.fetchall()}


def get_keyword_registered_counts(cursor):
    """등록된 키워드 수 (product_line별)"""
    cursor.execute("""
        SELECT product_line, COUNT(*) as cnt
        FROM market_mst WHERE analysis_type = 'trend'
        GROUP BY product_line
        ORDER BY product_line
    """)
    return {row[0]: row[1] for row in cursor.fetchall()}


def get_keyword_collected_counts(cursor, target_date_str):
    """수집된 고유 키워드 수 (product_line별)"""
    cursor.execute("""
        SELECT m.product_line, COUNT(DISTINCT t.keyword) as cnt
        FROM market_trend t
        INNER JOIN market_mst m ON m.analysis_type = 'trend' AND t.keyword = m.keyword
        WHERE DATE(t.crawl_at_local_time) = %s
        GROUP BY m.product_line
    """, (target_date_str,))
    return {row[0]: row[1] for row in cursor.fetchall()}


def get_missing_keywords(cursor, target_date_str):
    """누락된 키워드 목록 조회 (product_line별)"""
    cursor.execute("""
        SELECT m.product_line, m.keyword
        FROM market_mst m
        WHERE m.analysis_type = 'trend'
          AND NOT EXISTS (
              SELECT 1 FROM market_trend t
              WHERE t.keyword = m.keyword
                AND DATE(t.crawl_at_local_time) = %s
          )
        ORDER BY m.product_line, m.keyword
    """, (target_date_str,))
    missing_keywords_raw = cursor.fetchall()
    missing_keywords_by_pl = {}
    for row in missing_keywords_raw:
        pl = row[0]
        if pl not in missing_keywords_by_pl:
            missing_keywords_by_pl[pl] = []
        missing_keywords_by_pl[pl].append(row[1])
    return missing_keywords_by_pl


def get_market_avg_counts(cursor, target_date_str):
    """7일 평균 수집건수 (product_line + content_type별)"""
    cursor.execute("""
        SELECT
            product_line,
            content_type,
            ROUND(AVG(daily_count), 1) as avg_count
        FROM (
            SELECT
                m.product_line,
                m.content_type,
                DATE(t.crawl_at_local_time) as log_date,
                COUNT(*) as daily_count
            FROM market_trend t
            INNER JOIN market_mst m ON m.analysis_type = 'trend' AND t.keyword = m.keyword
            WHERE DATE(t.crawl_at_local_time) >= %s::date - INTERVAL '8 days'
              AND DATE(t.crawl_at_local_time) < %s::date
            GROUP BY m.product_line, m.content_type, DATE(t.crawl_at_local_time)
        ) daily_stats
        GROUP BY product_line, content_type
    """, (target_date_str, target_date_str))
    return {f"{row[0]}_{row[1]}": float(row[2] or 0) for row in cursor.fetchall()}


def get_market_trend_raw_data_list(cursor, target_date_str, category, content_type):
    """Market Trend 원본 데이터 조회"""
    columns = [
        'keyword', 'product_line', 'content_type', 'total_article_number',
        'calendar_week', 'crawl_at_local_time'
    ]

    if content_type:
        query = """
            SELECT
                t.keyword,
                m.product_line,
                m.content_type,
                t.total_article_number,
                t.calendar_week,
                t.crawl_at_local_time
            FROM market_trend t
            INNER JOIN market_mst m ON m.analysis_type = 'trend' AND t.keyword = m.keyword
            WHERE DATE(t.crawl_at_local_time) = %s
            AND m.product_line = %s
            AND m.content_type = %s
            ORDER BY t.crawl_at_local_time DESC
            LIMIT 500
        """
        cursor.execute(query, (target_date_str, category, content_type))
    else:
        query = """
            SELECT
                t.keyword,
                m.product_line,
                m.content_type,
                t.total_article_number,
                t.calendar_week,
                t.crawl_at_local_time
            FROM market_trend t
            INNER JOIN market_mst m ON m.analysis_type = 'trend' AND t.keyword = m.keyword
            WHERE DATE(t.crawl_at_local_time) = %s
            AND m.product_line = %s
            ORDER BY t.crawl_at_local_time DESC
            LIMIT 500
        """
        cursor.execute(query, (target_date_str, category))

    rows = cursor.fetchall()
    return columns, rows
