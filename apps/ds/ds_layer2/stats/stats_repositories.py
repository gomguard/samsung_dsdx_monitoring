"""
DS Layer 2 Stats Repository: 통계 전용 DB 접근(쿼리) 로직 격리
"""
from datetime import timedelta
from apps.common.db import ds_connection
from apps.common.targets import format_time
from apps.common.response import log_error


def fetch_batches_for_date(target_date):
    """특정 날짜의 배치 목록을 리테일러별로 그룹화하여 반환"""
    batches_by_retailer = {}
    try:
        with ds_connection() as (conn, cursor):
            query = """
                SELECT id, retailer, start_time, memo
                FROM ssd_crawl_db.ds_collection_batch_log
                WHERE date = %s
                ORDER BY retailer, start_time
            """
            cursor.execute(query, (target_date,))
            for row in cursor.fetchall():
                retailer = row[1]
                if retailer not in batches_by_retailer:
                    batches_by_retailer[retailer] = []
                batches_by_retailer[retailer].append({
                    'id': row[0],
                    'start_time': format_time(row[2]) if row[2] else '00:00',
                    'memo': row[3]
                })
    except Exception as e:
        log_error(e)
    return batches_by_retailer

def fetch_expected_count(cursor, country, mall_name):
    query = """
        SELECT COUNT(*) as cnt FROM samsung_ds_retail_com.samsung_price_tracking_list
        WHERE country = %s AND mall_name = %s AND is_active = 1
    """
    try:
        cursor.execute(query, (country, mall_name))
        result = cursor.fetchone()
        return result[0] if result else 0
    except Exception as e:
        log_error(e)
        return 0

def fetch_quality_counts(cursor, table_name, target_date):
    date_str = target_date.strftime('%Y%m%d')
    start_datetime = f"{date_str}0000"
    next_date = (target_date + timedelta(days=1)).strftime('%Y%m%d')
    end_datetime = f"{next_date}0000"
    return _do_quality_counts(cursor, table_name, start_datetime, end_datetime)

def fetch_quality_counts_by_time_range(cursor, table_name, target_date, start_time, end_time):
    date_str = target_date.strftime('%Y%m%d')
    start_datetime = f"{date_str}{start_time.replace(':', '')}00"
    if end_time:
        end_datetime = f"{date_str}{end_time.replace(':', '')}00"
    else:
        next_date = (target_date + timedelta(days=1)).strftime('%Y%m%d')
        end_datetime = f"{next_date}0000"
    return _do_quality_counts(cursor, table_name, start_datetime, end_datetime)

def _do_quality_counts(cursor, table_name, start_datetime, end_datetime):
    results = {
        'total': 0, 'title_null': 0, 'imageurl_null': 0, 'null_union': 0,
        'imageurl_invalid': 0, 'price_zero': 0, 'partial_null': 0, 'all_null': 0, 'valid': 0
    }
    try:
        base_query = f"SELECT DISTINCT * FROM samsung_ds_retail_com.{table_name} WHERE crawl_strdatetime >= %s AND crawl_strdatetime < %s"
        cursor.execute(f"SELECT COUNT(*) FROM ({base_query}) A", (start_datetime, end_datetime))
        results['total'] = cursor.fetchone()[0] or 0
        
        cursor.execute(f"SELECT COUNT(*) FROM ({base_query}) A WHERE title IS NULL OR TRIM(title) = ''", (start_datetime, end_datetime))
        results['title_null'] = cursor.fetchone()[0] or 0
        
        cursor.execute(f"SELECT COUNT(*) FROM ({base_query}) A WHERE imageurl IS NULL OR TRIM(imageurl) = ''", (start_datetime, end_datetime))
        results['imageurl_null'] = cursor.fetchone()[0] or 0
        
        cursor.execute(f"SELECT COUNT(*) FROM ({base_query}) A WHERE (title IS NULL OR TRIM(title) = '') OR (imageurl IS NULL OR TRIM(imageurl) = '')", (start_datetime, end_datetime))
        results['null_union'] = cursor.fetchone()[0] or 0
        
        cursor.execute(f"SELECT COUNT(*) FROM ({base_query}) A WHERE (title IS NOT NULL AND TRIM(title) != '') AND (imageurl IS NOT NULL AND TRIM(imageurl) != '') AND imageurl NOT LIKE 'https://%%'", (start_datetime, end_datetime))
        results['imageurl_invalid'] = cursor.fetchone()[0] or 0
        
        cursor.execute(f"SELECT COUNT(*) FROM ({base_query}) A WHERE (title IS NOT NULL AND TRIM(title) != '') AND (retailprice = '0' OR retailprice REGEXP '^\\$?0(\\.0+)?$')", (start_datetime, end_datetime))
        results['price_zero'] = cursor.fetchone()[0] or 0
        
        valid_base = f"SELECT * FROM ({base_query}) A WHERE (title IS NOT NULL AND TRIM(title) != '') AND (imageurl IS NOT NULL AND imageurl LIKE 'https://%%')"
        
        cursor.execute(f"SELECT COUNT(*) FROM ({valid_base}) B WHERE (retailprice IS NULL OR TRIM(retailprice) = '') AND (ships_from IS NULL OR TRIM(ships_from) = '') AND (sold_by IS NULL OR TRIM(sold_by) = '')", (start_datetime, end_datetime))
        results['all_null'] = cursor.fetchone()[0] or 0
        
        cursor.execute(f"SELECT COUNT(*) FROM ({valid_base}) B WHERE NOT ( ((retailprice IS NOT NULL AND TRIM(retailprice) != '') AND (ships_from IS NOT NULL AND TRIM(ships_from) != '') AND (sold_by IS NOT NULL AND TRIM(sold_by) != '')) OR ((retailprice IS NULL OR TRIM(retailprice) = '') AND (ships_from IS NULL OR TRIM(ships_from) = '') AND (sold_by IS NULL OR TRIM(sold_by) = '')) )", (start_datetime, end_datetime))
        results['partial_null'] = cursor.fetchone()[0] or 0
        
        cursor.execute(f"SELECT COUNT(*) FROM ({valid_base}) B WHERE (retailprice IS NOT NULL AND TRIM(retailprice) != '') AND (ships_from IS NOT NULL AND TRIM(ships_from) != '') AND (sold_by IS NOT NULL AND TRIM(sold_by) != '')", (start_datetime, end_datetime))
        results['valid'] = cursor.fetchone()[0] or 0
        
    except Exception as e:
        results['error'] = log_error(e)
    return results

def fetch_table_null_detail(table_name, target_date, error_type, page, page_size, start_time, end_time, sort_by, sort_order):
    try:
        with ds_connection() as (conn, cursor):
            date_str_fmt = target_date.strftime('%Y%m%d')
            start_datetime = f"{date_str_fmt}{start_time.replace(':', '')}00" if start_time else f"{date_str_fmt}0000"
            if end_time and end_time != '다음날':
                end_datetime = f"{date_str_fmt}{end_time.replace(':', '')}00"
            else:
                end_datetime = f"{(target_date + timedelta(days=1)).strftime('%Y%m%d')}0000"
            
            valid_sort_columns = ['crawl_strdatetime', 'title', 'retailprice', 'ships_from', 'sold_by']
            if sort_by not in valid_sort_columns: sort_by = 'crawl_strdatetime'
            sort_direction = 'DESC' if sort_order.lower() == 'desc' else 'ASC'
            
            base_query = f"SELECT DISTINCT * FROM samsung_ds_retail_com.{table_name} WHERE crawl_strdatetime >= %s AND crawl_strdatetime < %s"
            
            if error_type == 'title_null':
                where_condition = "WHERE title IS NULL OR TRIM(title) = ''"
            elif error_type == 'imageurl_null':
                where_condition = "WHERE imageurl IS NULL OR TRIM(imageurl) = ''"
            elif error_type == 'imageurl_invalid':
                where_condition = "WHERE (title IS NOT NULL AND TRIM(title) != '') AND (imageurl IS NOT NULL AND TRIM(imageurl) != '') AND imageurl NOT LIKE 'https://%%'"
            elif error_type == 'price_zero':
                where_condition = "WHERE (title IS NOT NULL AND TRIM(title) != '') AND (retailprice = '0' OR retailprice REGEXP '^\\$?0(\\.0+)?$')"
            else:
                where_condition = "WHERE (title IS NOT NULL AND TRIM(title) != '') AND (imageurl IS NOT NULL AND imageurl LIKE 'https://%%') AND NOT ( ((retailprice IS NOT NULL AND TRIM(retailprice) != '') AND (ships_from IS NOT NULL AND TRIM(ships_from) != '') AND (sold_by IS NOT NULL AND TRIM(sold_by) != '')) OR ((retailprice IS NULL OR TRIM(retailprice) = '') AND (ships_from IS NULL OR TRIM(ships_from) = '') AND (sold_by IS NULL OR TRIM(sold_by) = '')) )"
            
            cursor.execute(f"SELECT COUNT(*) FROM ({base_query}) A {where_condition}", (start_datetime, end_datetime))
            total_count = cursor.fetchone()[0]
            
            offset = (page - 1) * page_size
            query = f"SELECT title, retailprice, ships_from, sold_by, imageurl, producturl, retailersku, crawl_strdatetime FROM ({base_query}) A {where_condition} ORDER BY {sort_by} {sort_direction} LIMIT %s OFFSET %s"
            cursor.execute(query, (start_datetime, end_datetime, page_size, offset))
            rows = cursor.fetchall()
            
            return {'total_count': total_count, 'rows': rows}
    except Exception as e:
        log_error(e)
        return None
