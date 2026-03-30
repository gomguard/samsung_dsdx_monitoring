from apps.common.common_repositories import execute_ds_scalar, execute_ds_query_dict

def get_crawl_count_db(table_name, start_datetime, end_datetime):
    query = f"""
        SELECT COUNT(*) as cnt FROM (
            SELECT DISTINCT * FROM samsung_ds_retail_com.{table_name}
            WHERE crawl_strdatetime >= %s AND crawl_strdatetime < %s
        ) A
    """
    try:
        count = execute_ds_scalar(query, (start_datetime, end_datetime))
        return count if count is not None else 0
    except Exception:
        return -1

def get_expected_count_db(country, mall_name):
    query = """
        SELECT COUNT(*) as cnt FROM samsung_ds_retail_com.samsung_price_tracking_list
        WHERE country = %s AND mall_name = %s AND is_active = 1
    """
    try:
        count = execute_ds_scalar(query, (country, mall_name))
        return count if count is not None else 0
    except Exception:
        return -1

def get_closed_report_stats_db(target_date):
    query = """
        SELECT t.retailer, r.expected_count, r.total_count, r.completion_rate, r.final_batch_count
        FROM ssd_crawl_db.ds_monitoring_report_daily r
        JOIN ssd_crawl_db.ds_monitoring_targets t ON r.retailer_id = t.retailer_id
        WHERE r.crawl_date = %s AND r.is_del = 0
    """
    try:
        return execute_ds_query_dict(query, (target_date,))
    except Exception:
        return []

def get_table_detail_count_db(table_name, start_datetime, end_datetime):
    query = f"""
        SELECT COUNT(*) FROM (
            SELECT DISTINCT * FROM samsung_ds_retail_com.{table_name}
            WHERE crawl_strdatetime >= %s AND crawl_strdatetime < %s
        ) A
    """
    try:
        count = execute_ds_scalar(query, (start_datetime, end_datetime))
        return count if count is not None else 0
    except Exception:
        return 0

def get_table_detail_db(table_name, start_datetime, end_datetime, sort_by, sort_direction, page_size, offset):
    valid_sort_columns = ['crawl_strdatetime', 'title', 'retailprice', 'ships_from', 'sold_by']
    if sort_by not in valid_sort_columns:
        sort_by = 'crawl_strdatetime'
    direction = 'DESC' if sort_direction.upper() == 'DESC' else 'ASC'

    query = f"""
        SELECT title, retailprice, ships_from, sold_by, imageurl, producturl, crawl_strdatetime
        FROM (
            SELECT DISTINCT * FROM samsung_ds_retail_com.{table_name}
            WHERE crawl_strdatetime >= %s AND crawl_strdatetime < %s
        ) A
        ORDER BY {sort_by} {direction}, title
        LIMIT %s OFFSET %s
    """
    try:
        return execute_ds_query_dict(query, (start_datetime, end_datetime, page_size, offset))
    except Exception:
        return []
