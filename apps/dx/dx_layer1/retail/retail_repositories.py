"""
DX Layer 1 Retail Repositories: 데이터베이스 I/O 쿼리 전담 계층
"""

def query_retail_counts(cursor, table_name, date_field, extra_rank_field, slot_start, slot_end, daily_retailers=None):
    if daily_retailers:
        date_only = slot_start[:10]
        daily_list = list(daily_retailers)
        daily_placeholders = ','.join(['%s'] * len(daily_list))
        cursor.execute(f"""
            SELECT account_name,
                   COUNT(*) as cnt,
                   COUNT(CASE WHEN main_rank IS NOT NULL THEN 1 END) as main_count,
                   COUNT(CASE WHEN bsr_rank IS NOT NULL THEN 1 END) as bsr_count,
                   COUNT(CASE WHEN {extra_rank_field} IS NOT NULL THEN 1 END) as extra_count
            FROM {table_name}
            WHERE (
                (LOWER(account_name) IN ({daily_placeholders}) AND DATE({date_field}) = %s)
                OR
                (LOWER(account_name) NOT IN ({daily_placeholders}) AND {date_field} >= %s AND {date_field} < %s)
            )
            GROUP BY account_name
        """, daily_list + [date_only] + daily_list + [slot_start, slot_end])
    else:
        cursor.execute(f"""
            SELECT account_name,
                   COUNT(*) as cnt,
                   COUNT(CASE WHEN main_rank IS NOT NULL THEN 1 END) as main_count,
                   COUNT(CASE WHEN bsr_rank IS NOT NULL THEN 1 END) as bsr_count,
                   COUNT(CASE WHEN {extra_rank_field} IS NOT NULL THEN 1 END) as extra_count
            FROM {table_name}
            WHERE {date_field} >= %s
            AND {date_field} < %s
            GROUP BY account_name
        """, (slot_start, slot_end))
    return cursor.fetchall()


def query_retail_counts_by_retailer(cursor, table_name, date_field, extra_rank_field, slot_start, slot_end, retailer):
    cursor.execute(f"""
        SELECT
            COUNT(CASE WHEN main_rank IS NOT NULL THEN 1 END) as main_count,
            COUNT(CASE WHEN bsr_rank IS NOT NULL THEN 1 END) as bsr_count,
            COUNT(CASE WHEN {extra_rank_field} IS NOT NULL THEN 1 END) as extra_count,
            COUNT(*) as total
        FROM {table_name}
        WHERE {date_field} >= %s
        AND {date_field} < %s
        AND LOWER(account_name) = LOWER(%s)
    """, (slot_start, slot_end, retailer))
    return cursor.fetchone()


def get_tv_retail_detail_list(cursor, target_date):
    cursor.execute("""
        SELECT
            account_name as retailer,
            COUNT(*) as total,
            COUNT(CASE WHEN main_rank IS NOT NULL THEN 1 END) as main_count,
            COUNT(CASE WHEN bsr_rank IS NOT NULL THEN 1 END) as bsr_count,
            COUNT(CASE WHEN final_sku_price IS NOT NULL THEN 1 END) as price_count
        FROM tv_retail_com
        WHERE DATE(crawl_datetime::timestamp) = %s
        GROUP BY account_name
        ORDER BY account_name
    """, (target_date,))
    return cursor.fetchall()


def query_daily_category_counts(cursor, table_name, date_field, target_date, retailers):
    placeholders = ','.join(['%s'] * len(retailers))
    cursor.execute(f"""
        SELECT account_name,
               COUNT(*) as cnt,
               COUNT(CASE WHEN LOWER(page_type) = 'main' THEN 1 END) as main_count,
               COUNT(CASE WHEN LOWER(page_type) = 'bsr' THEN 1 END) as bsr_count,
               0 as extra_count
        FROM {table_name}
        WHERE DATE({date_field}::timestamp) = %s
        AND account_name IN ({placeholders})
        GROUP BY account_name
        ORDER BY account_name
    """, [target_date] + list(retailers))
    return cursor.fetchall()


def query_daily_category_summary_by_retailer(cursor, table_name, date_field, target_date, retailer):
    cursor.execute(f"""
        SELECT
            COUNT(CASE WHEN LOWER(page_type) = 'main' THEN 1 END) as main_count,
            COUNT(CASE WHEN LOWER(page_type) = 'bsr' THEN 1 END) as bsr_count,
            0 as extra_count,
            COUNT(*) as total
        FROM {table_name}
        WHERE DATE({date_field}::timestamp) = %s
        AND account_name = %s
    """, (target_date, retailer))
    return cursor.fetchone()


def get_hhp_retail_detail_list(cursor, target_date):
    return []

    cursor.execute("""
        SELECT
            account_name as retailer,
            COUNT(*) as total,
            COUNT(CASE WHEN main_rank IS NOT NULL THEN 1 END) as main_count,
            COUNT(CASE WHEN bsr_rank IS NOT NULL THEN 1 END) as bsr_count,
            COUNT(CASE WHEN final_sku_price IS NOT NULL THEN 1 END) as price_count
        FROM hhp_retail_com
        WHERE DATE(crawl_strdatetime::timestamp) = %s
        GROUP BY account_name
        ORDER BY account_name
    """, (target_date,))
    return cursor.fetchall()


def get_retail_summary_null_counts(cursor, table_name, date_field, check_columns, slot_start, slot_end, retailer, is_daily):
    count_parts = [f"COUNT({col}) as {col}_cnt" for col in check_columns]
    if is_daily:
        date_only = slot_start[:10]
        query = f"""
            SELECT {', '.join(count_parts)}
            FROM {table_name}
            WHERE DATE({date_field}::timestamp) = %s
            AND LOWER(account_name) = LOWER(%s)
        """
        cursor.execute(query, (date_only, retailer))
    else:
        query = f"""
            SELECT {', '.join(count_parts)}
            FROM {table_name}
            WHERE {date_field} >= %s
            AND {date_field} < %s
            AND LOWER(account_name) = LOWER(%s)
        """
        cursor.execute(query, (slot_start, slot_end, retailer))
    return cursor.fetchone()


def get_retailer_raw_data_list(cursor, table_name, columns, retailer, date_column, start_time, end_time):
    query = f"""
        SELECT {', '.join(columns)}
        FROM {table_name}
        WHERE LOWER(account_name) = LOWER(%s)
        AND {date_column}::timestamp >= %s
        AND {date_column}::timestamp < %s
        ORDER BY id DESC
        LIMIT 500
    """
    cursor.execute(query, (retailer, start_time, end_time))
    return cursor.fetchall()
