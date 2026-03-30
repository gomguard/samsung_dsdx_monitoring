"""
DS Layer 4 Screenshot Repository: 스크린샷 캡쳐 관련 Raw SQL 전담 
"""
from datetime import datetime, timedelta
from apps.common.db import ds_connection
from config.config import SSM_CONFIG

def get_screenshot_file_info(file_id):
    """file_id에 해당하는 파일 정보 조회"""
    with ds_connection() as (conn, cursor):
        cursor.execute("""
            SELECT file_path, file_name, file_type
            FROM ssd_crawl_db.ds_monitoring_file
            WHERE file_id = %s AND is_del = 0
        """, (file_id,))
        return cursor.fetchone()

def get_retailer_instance_info(retailer):
    """리테일러의 instance 캡쳐 정보 조회"""
    with ds_connection() as (conn, cursor):
        cursor.execute("""
            SELECT retailer_id, instance_id, instance_region, mall_name FROM ssd_crawl_db.ds_monitoring_targets
            WHERE retailer = %s AND is_active = 1
        """, (retailer,))
        return cursor.fetchone()

def expire_running_captures(retailer_id, crawl_date, time_limit_minutes=30):
    """비정상적으로 징시간 running 상태인 로그 실패 처리"""
    with ds_connection() as (conn, cursor):
        cursor.execute("""
            UPDATE ssd_crawl_db.ds_monitoring_capture_log
            SET status = 'failed'
            WHERE retailer_id = %s AND crawl_date = %s AND status = 'running'
            AND triggered_at < %s
        """, (retailer_id, crawl_date, datetime.now() - timedelta(minutes=time_limit_minutes)))
        if cursor.rowcount > 0:
            conn.commit()

def get_latest_running_capture(retailer_id, crawl_date):
    """현재 running 상태인 최근 캡쳐 로그 조회"""
    with ds_connection() as (conn, cursor):
        cursor.execute("""
            SELECT id, triggered_at FROM ssd_crawl_db.ds_monitoring_capture_log
            WHERE retailer_id = %s AND crawl_date = %s AND status = 'running'
            ORDER BY triggered_at DESC LIMIT 1
        """, (retailer_id, crawl_date))
        return cursor.fetchone()

def insert_capture_log(retailer_id, crawl_date, triggered_id):
    """스크린샷 캡쳐 스케줄러 트리거 로그 등록"""
    with ds_connection() as (conn, cursor):
        cursor.execute("""
            INSERT INTO ssd_crawl_db.ds_monitoring_capture_log
            (retailer_id, crawl_date, triggered_at, triggered_id, status)
            VALUES (%s, %s, %s, %s, 'running')
        """, (retailer_id, crawl_date, datetime.now(), triggered_id))
        conn.commit()

def get_screenshot_status_summary(retailer, crawl_date):
    """리테일러별 스크린샷 캡쳐 상태 종합 조회"""
    with ds_connection() as (conn, cursor):
        cursor.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN a.screenshot_id IS NOT NULL THEN 1 ELSE 0 END) as captured
            FROM ssd_crawl_db.ds_monitoring_report_anomaly a
            JOIN ssd_crawl_db.ds_monitoring_targets t ON a.retailer_id = t.retailer_id
            WHERE LOWER(t.retailer) = LOWER(%s) AND a.crawl_date = %s AND a.is_del = 0
        """, (retailer, crawl_date))
        total_row = cursor.fetchone()

        cursor.execute("""
            SELECT cl.id, cl.triggered_at
            FROM ssd_crawl_db.ds_monitoring_capture_log cl
            JOIN ssd_crawl_db.ds_monitoring_targets t ON cl.retailer_id = t.retailer_id
            WHERE LOWER(t.retailer) = LOWER(%s) AND cl.crawl_date = %s AND cl.status = 'running'
            ORDER BY cl.triggered_at DESC LIMIT 1
        """, (retailer, crawl_date))
        log_row = cursor.fetchone()

        return total_row, log_row

def soft_delete_screenshots(anomaly_ids):
    """anomaly_id 목록에 해당하는 스크린샷 정보 초기화 및 file soft delete"""
    with ds_connection() as (conn, cursor):
        placeholders = ','.join(['%s'] * len(anomaly_ids))
        cursor.execute(f"""
            SELECT id, screenshot_id FROM ssd_crawl_db.ds_monitoring_report_anomaly
            WHERE id IN ({placeholders}) AND screenshot_id IS NOT NULL AND is_del = 0
        """, anomaly_ids)
        anomaly_rows = cursor.fetchall()
        
        if not anomaly_rows:
            return None

        screenshot_ids = [row[1] for row in anomaly_rows]
        target_anomaly_ids = [row[0] for row in anomaly_rows]

        file_placeholders = ','.join(['%s'] * len(screenshot_ids))
        cursor.execute(f"""
            SELECT file_id, file_path, file_name FROM ssd_crawl_db.ds_monitoring_file
            WHERE file_id IN ({file_placeholders}) AND is_del = 0
        """, screenshot_ids)
        file_rows = cursor.fetchall()

        cursor.execute(f"""
            UPDATE ssd_crawl_db.ds_monitoring_file
            SET is_del = 1
            WHERE file_id IN ({file_placeholders})
        """, screenshot_ids)

        anomaly_placeholders = ','.join(['%s'] * len(target_anomaly_ids))
        cursor.execute(f"""
            UPDATE ssd_crawl_db.ds_monitoring_report_anomaly
            SET screenshot_id = NULL
            WHERE id IN ({anomaly_placeholders})
        """, target_anomaly_ids)

        conn.commit()

        return file_rows, len(target_anomaly_ids)

def get_anomaly_for_upload(anomaly_id):
    """업로드를 위한 anomaly 리테일러 및 날짜 정보 조회"""
    with ds_connection() as (conn, cursor):
        cursor.execute("""
            SELECT a.id, t.retailer, a.crawl_date, a.retailersku
            FROM ssd_crawl_db.ds_monitoring_report_anomaly a
            LEFT JOIN ssd_crawl_db.ds_monitoring_targets t ON a.retailer_id = t.retailer_id
            WHERE a.id = %s AND a.is_del = 0
        """, (anomaly_id,))
        return cursor.fetchone()

def insert_uploaded_file(file_name, file_path, file_size, file_type, created_id, anomaly_id):
    """업로드된 파일 메타데이터 저장 및 anomaly 연결"""
    with ds_connection() as (conn, cursor):
        now = datetime.now()
        cursor.execute("""
            INSERT INTO ssd_crawl_db.ds_monitoring_file
            (file_name, file_path, file_size, file_type, is_del, created_at, created_id)
            VALUES (%s, %s, %s, %s, 0, %s, %s)
        """, (file_name, file_path, file_size, file_type, now, created_id))
        file_id = cursor.lastrowid

        cursor.execute("""
            UPDATE ssd_crawl_db.ds_monitoring_report_anomaly
            SET screenshot_id = %s
            WHERE id = %s
        """, (file_id, anomaly_id))

        conn.commit()
        return file_id
