from apps.common.db import ds_connection
from apps.common.common_repositories import execute_ds_query_dict

def get_retailer_info_db(retailer):
    """DB에서 해당 리테일러의 인스턴스 정보 조회"""
    query = """
        SELECT retailer_id, instance_id, instance_region, schedule_name, region_timezone
        FROM ssd_crawl_db.ds_monitoring_targets
        WHERE retailer = %s AND is_active = 1
    """
    results = execute_ds_query_dict(query, (retailer,))
    return results[0] if results else None
    
def save_rerun_log_db(retailer_id, retailer, crawl_date, schedule_name, created_id, instance_id, command_id, batch_start_time, batch_memo, now):
    """재실행 로그 기록 및 수집 배치 로그 동시 저장 (트랜잭션 묶음)"""
    with ds_connection() as (conn, cursor):
        cursor.execute("""
            INSERT INTO ssd_crawl_db.ds_monitoring_crawler_rerun_log
            (retailer_id, crawl_date, schedule_name, created_id, instance_id, command_id, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (retailer_id, crawl_date, schedule_name, created_id, instance_id, command_id, now))

        cursor.execute("""
            INSERT INTO ssd_crawl_db.ds_collection_batch_log
            (date, retailer, start_time, memo)
            VALUES (%s, %s, %s, %s)
        """, (crawl_date, retailer, batch_start_time, batch_memo))

        conn.commit()
