"""
DX Layer 1 Sentiment Repositories: 데이터베이스 I/O 쿼리 전담 계층
"""

def get_target_total(cursor, category, target_date_str):
    cursor.execute("""
        SELECT COALESCE(SUM(target_count), 0)
        FROM retail_sentiment_analysis_log
        WHERE category = %s AND analysis_date = %s
    """, (category, target_date_str))
    return cursor.fetchone()[0] or 0


def get_analyzed_total(cursor, sentiment_table, com_table, crawl_col, start_time, end_time):
    cursor.execute(f"""
        SELECT COUNT(*)
        FROM {sentiment_table} s
        JOIN {com_table} r ON s.retail_com_id = r.id
        WHERE r.{crawl_col}::timestamp >= %s AND r.{crawl_col}::timestamp < %s
    """, (start_time, end_time))
    return cursor.fetchone()[0] or 0


def get_target_details(cursor, category, target_date_str):
    cursor.execute("""
        SELECT retailer, period, target_count
        FROM retail_sentiment_analysis_log
        WHERE category = %s AND analysis_date = %s
    """, (category, target_date_str))
    return {f"{row[0]}_{row[1]}": row[2] for row in cursor.fetchall()}


def get_analyzed_details(cursor, sentiment_table, com_table, crawl_col, start_time, end_time):
    cursor.execute(f"""
        SELECT
            LOWER(r.account_name),
            CASE WHEN EXTRACT(HOUR FROM r.{crawl_col}::timestamp) < 12 THEN '오전' ELSE '오후' END as period,
            COUNT(*) as analyzed_count
        FROM {sentiment_table} s
        JOIN {com_table} r ON s.retail_com_id = r.id
        WHERE r.{crawl_col}::timestamp >= %s AND r.{crawl_col}::timestamp < %s
        GROUP BY LOWER(r.account_name), period
        ORDER BY LOWER(r.account_name), period
    """, (start_time, end_time))
    return {f"{row[0]}_{row[1]}": row[2] for row in cursor.fetchall()}


def get_sentiment_raw_data_list(cursor, category, retailer, start_time, end_time):
    columns = [
        'id', 'retail_com_id', 'item', 'sentiment_score',
        'final_interpretation', 'created_at', 'batch_id'
    ]

    if category == 'TV':
        query = """
            SELECT
                s.id,
                s.retail_com_id,
                r.item,
                s.sentiment_score,
                s.final_interpretation,
                s.created_at,
                s.batch_id
            FROM tv_retail_sentiment s
            JOIN tv_retail_com r ON s.retail_com_id = r.id
            WHERE LOWER(r.account_name) = LOWER(%s)
            AND r.crawl_datetime >= %s
            AND r.crawl_datetime < %s
            ORDER BY s.id DESC
            LIMIT 500
        """
    else:
        query = """
            SELECT
                s.id,
                s.retail_com_id,
                r.item,
                s.sentiment_score,
                s.final_interpretation,
                s.created_at,
                s.batch_id
            FROM hhp_retail_sentiment s
            JOIN hhp_retail_com r ON s.retail_com_id = r.id
            WHERE LOWER(r.account_name) = LOWER(%s)
            AND r.crawl_strdatetime >= %s
            AND r.crawl_strdatetime < %s
            ORDER BY s.id DESC
            LIMIT 500
        """

    cursor.execute(query, (retailer, start_time, end_time))
    return columns, cursor.fetchall()
