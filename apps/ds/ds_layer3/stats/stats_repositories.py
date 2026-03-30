"""
DS Layer 3 Stats Repository: SKU 이상치 원천 데이터 조회 전담
오직 데이터베이스 엔진에 Raw Query를 날려 데이터를 꺼내오는 역할만 수행합니다.
"""
from datetime import timedelta
from apps.common.targets import load_monitoring_targets

def get_monitoring_targets():
    """CSV에서 모니터링 대상 목록 로드"""
    return load_monitoring_targets()

def get_closed_dates(cursor, start_date, end_date):
    """날짜 범위 내 마감된 날짜 집합 조회"""
    cursor.execute("""
        SELECT crawl_date FROM ssd_crawl_db.ds_monitoring_report_close
        WHERE crawl_date BETWEEN %s AND %s AND is_closed = 1
    """, (start_date, end_date))
    return set(row[0] for row in cursor.fetchall())

def get_retailer_id_map(cursor):
    """리테일러명 → retailer_id 매핑"""
    cursor.execute("""
        SELECT retailer, retailer_id FROM ssd_crawl_db.ds_monitoring_targets
        WHERE is_active = 1
    """)
    return {row[0]: row[1] for row in cursor.fetchall()}

def get_anomaly_skus_from_report(cursor, retailer_id, crawl_date):
    """마감된 날짜의 이상치 SKU 목록 (report_anomaly 테이블)"""
    cursor.execute("""
        SELECT retailersku, title, retailprice, ships_from, sold_by,
               imageurl, producturl, cause, memo, screenshot_id
        FROM ssd_crawl_db.ds_monitoring_report_anomaly
        WHERE crawl_date = %s AND retailer_id = %s AND is_del = 0
          AND retailersku IS NOT NULL AND TRIM(retailersku) != ''
    """, (crawl_date, retailer_id))

    results = []
    for row in cursor.fetchall():
        results.append({
            'retailersku': row[0],
            'title': row[1] or '',
            'retailprice': row[2] or '',
            'ships_from': row[3] or '',
            'sold_by': row[4] or '',
            'imageurl': row[5] or '',
            'producturl': row[6] or '',
            'cause': row[7] or '',
            'memo': row[8] or '',
            'screenshot_id': row[9]
        })
    return results

def get_anomaly_skus_from_realtime(cursor, table_name, target_date):
    """미마감 날짜의 이상치 SKU 목록 (원본 테이블 실시간 쿼리)"""
    date_str = target_date.strftime('%Y%m%d')
    start_datetime = f"{date_str}0000"
    next_date = (target_date + timedelta(days=1)).strftime('%Y%m%d')
    end_datetime = f"{next_date}0000"

    base_query = f"""
        SELECT DISTINCT * FROM samsung_ds_retail_com.{table_name}
        WHERE crawl_strdatetime >= %s AND crawl_strdatetime < %s
    """

    query = f"""
        SELECT DISTINCT retailersku, title, retailprice, ships_from, sold_by,
               imageurl, producturl
        FROM ({base_query}) A
        WHERE (
            (title IS NULL OR TRIM(title) = '')
            OR (imageurl IS NULL OR TRIM(imageurl) = '')
            OR ((title IS NOT NULL AND TRIM(title) != '')
                AND (imageurl IS NOT NULL AND TRIM(imageurl) != '')
                AND imageurl NOT LIKE 'https://%%')
            OR ((title IS NOT NULL AND TRIM(title) != '')
                AND (imageurl IS NOT NULL AND imageurl LIKE 'https://%%')
                AND NOT (
                    ((retailprice IS NOT NULL AND TRIM(retailprice) != '')
                     AND (ships_from IS NOT NULL AND TRIM(ships_from) != '')
                     AND (sold_by IS NOT NULL AND TRIM(sold_by) != ''))
                    OR
                    ((retailprice IS NULL OR TRIM(retailprice) = '')
                     AND (ships_from IS NULL OR TRIM(ships_from) = '')
                     AND (sold_by IS NULL OR TRIM(sold_by) = ''))
                ))
            OR ((title IS NOT NULL AND TRIM(title) != '')
                AND (retailprice = '0' OR retailprice REGEXP '^\\\\$?0(\\\\.0+)?$'))
        )
        AND retailersku IS NOT NULL AND TRIM(retailersku) != ''
    """

    cursor.execute(query, (start_datetime, end_datetime))
    results = []
    for row in cursor.fetchall():
        results.append({
            'retailersku': row[0],
            'title': row[1] or '',
            'retailprice': row[2] or '',
            'ships_from': row[3] or '',
            'sold_by': row[4] or '',
            'imageurl': row[5] or '',
            'producturl': row[6] or '',
        })
    return results

def build_sku_day_map(cursor, retailer_id, table_name, start_date, end_date, closed_dates):
    """날짜 범위 내 SKU별 이상치 출현 상황을 DB에서 조회하여 집계합니다."""
    sku_map = {}
    current = start_date

    while current <= end_date:
        if current in closed_dates:
            day_skus = get_anomaly_skus_from_report(cursor, retailer_id, current)
        else:
            day_skus = get_anomaly_skus_from_realtime(cursor, table_name, current)

        for item in day_skus:
            sku = item['retailersku']
            if sku not in sku_map:
                sku_map[sku] = {
                    'days': {},
                    'latest': None,
                    'latest_cause': '',
                    'latest_memo': '',
                    'latest_screenshot_id': None,
                }

            sku_map[sku]['days'][current] = item
            sku_map[sku]['latest'] = item

            if item.get('cause'):
                sku_map[sku]['latest_cause'] = item['cause']
            if item.get('memo'):
                sku_map[sku]['latest_memo'] = item['memo']
            if item.get('screenshot_id'):
                sku_map[sku]['latest_screenshot_id'] = item['screenshot_id']

        current += timedelta(days=1)

    # 미마감 날짜의 cause/memo 보충 처리
    if sku_map:
        cursor.execute("""
            SELECT retailersku, cause, memo, screenshot_id, crawl_date
            FROM ssd_crawl_db.ds_monitoring_report_anomaly
            WHERE retailer_id = %s AND crawl_date BETWEEN %s AND %s AND is_del = 0
              AND retailersku IS NOT NULL AND TRIM(retailersku) != ''
        """, (retailer_id, start_date, end_date))
        for row in cursor.fetchall():
            sku = row[0]
            if sku not in sku_map:
                continue
            cause = row[1] or ''
            memo = row[2] or ''
            screenshot_id = row[3]
            crawl_date = row[4]

            if crawl_date in sku_map[sku]['days']:
                sku_map[sku]['days'][crawl_date]['cause'] = cause
                sku_map[sku]['days'][crawl_date]['memo'] = memo
                sku_map[sku]['days'][crawl_date]['screenshot_id'] = screenshot_id

            if cause:
                sku_map[sku]['latest_cause'] = cause
            if memo:
                sku_map[sku]['latest_memo'] = memo
            if screenshot_id:
                sku_map[sku]['latest_screenshot_id'] = screenshot_id

    return sku_map
