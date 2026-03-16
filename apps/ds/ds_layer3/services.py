"""
DS Layer 3 Service: SKU 이상치 반복 패턴 분석
마감된 날짜는 report_anomaly 스냅샷, 미마감은 원본 테이블 실시간 쿼리
"""

from datetime import datetime, timedelta
from apps.common.db import ds_connection
from apps.common.targets import load_monitoring_targets
from apps.common.response import log_error


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
    """
    날짜 범위 내 SKU별 이상치 출현 맵 구성

    Returns:
        dict: {
            'SKU123': {
                'days': {date: {product_data}, ...},
                'latest': {최신 날짜의 제품 데이터},
                'latest_cause': str,
                'latest_memo': str,
                'latest_screenshot_id': int or None,
            }
        }
    """
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

            # 최신 데이터 갱신 (날짜순 순회하므로 마지막이 최신)
            sku_map[sku]['latest'] = item
            if item.get('cause'):
                sku_map[sku]['latest_cause'] = item['cause']
            if item.get('memo'):
                sku_map[sku]['latest_memo'] = item['memo']
            if item.get('screenshot_id'):
                sku_map[sku]['latest_screenshot_id'] = item['screenshot_id']

        current += timedelta(days=1)

    # 미마감 날짜의 cause/memo를 report_anomaly에서 보충
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
            # days에 해당 날짜 데이터가 있으면 cause/memo 보충
            if crawl_date in sku_map[sku]['days']:
                sku_map[sku]['days'][crawl_date]['cause'] = cause
                sku_map[sku]['days'][crawl_date]['memo'] = memo
                sku_map[sku]['days'][crawl_date]['screenshot_id'] = screenshot_id
            # 최신 cause/memo 갱신
            if cause:
                sku_map[sku]['latest_cause'] = cause
            if memo:
                sku_map[sku]['latest_memo'] = memo
            if screenshot_id:
                sku_map[sku]['latest_screenshot_id'] = screenshot_id

    return sku_map


def calc_consecutive_days(day_map, end_date):
    """end_date부터 역순으로 연속 출현일 수 계산"""
    if end_date not in day_map:
        return 0
    count = 1
    check_date = end_date - timedelta(days=1)
    while check_date in day_map:
        count += 1
        check_date -= timedelta(days=1)
    return count


def get_layer_stats(target_date, days):
    """전체 리테일러별 SKU 이상치 요약 통계"""
    start_date = target_date - timedelta(days=days - 1)

    data = {
        'timestamp': datetime.now().isoformat(),
        'date': str(target_date),
        'days': days,
        'layer': 3,
        'data_source': 'ds',
        'results': [],
        'summary': {}
    }

    try:
        with ds_connection() as (conn, cursor):
            closed_dates = get_closed_dates(cursor, start_date, target_date)
            retailer_id_map = get_retailer_id_map(cursor)

            results = []
            total_anomaly_skus = 0
            total_repeat_skus = 0
            total_new_skus = 0

            for idx, (table_name, retailer, region, korea_time, country, mall_name) in enumerate(get_monitoring_targets(), 1):
                retailer_id = retailer_id_map.get(retailer)
                if not retailer_id:
                    results.append({
                        'no': idx, 'table_name': table_name, 'retailer': retailer,
                        'region': region, 'country': country.upper(),
                        'total_anomaly_skus': 0, 'repeat_skus': 0, 'new_skus': 0,
                        'max_consecutive_days': 0, 'status': 'success'
                    })
                    continue

                try:
                    sku_map = build_sku_day_map(cursor, retailer_id, table_name, start_date, target_date, closed_dates)

                    # 기준일에 이상치인 SKU만 집계
                    anomaly_skus = 0
                    repeat_skus = 0
                    new_skus = 0
                    max_consecutive = 0

                    for sku, info in sku_map.items():
                        consecutive = calc_consecutive_days(info['days'], target_date)
                        if consecutive == 0:
                            continue  # 기준일에 없는 SKU
                        anomaly_skus += 1
                        if consecutive >= 2:
                            repeat_skus += 1
                        else:
                            new_skus += 1
                        if consecutive > max_consecutive:
                            max_consecutive = consecutive

                    total_anomaly_skus += anomaly_skus
                    total_repeat_skus += repeat_skus
                    total_new_skus += new_skus

                    status = 'success' if anomaly_skus == 0 else 'danger'

                    results.append({
                        'no': idx,
                        'table_name': table_name,
                        'retailer': retailer,
                        'region': region,
                        'country': country.upper(),
                        'total_anomaly_skus': anomaly_skus,
                        'repeat_skus': repeat_skus,
                        'new_skus': new_skus,
                        'max_consecutive_days': max_consecutive,
                        'status': status
                    })
                except Exception as e:
                    results.append({
                        'no': idx, 'table_name': table_name, 'retailer': retailer,
                        'region': region, 'country': country.upper(),
                        'total_anomaly_skus': 0, 'repeat_skus': 0, 'new_skus': 0,
                        'max_consecutive_days': 0, 'status': 'error', 'error': log_error(e)
                    })

            overall_status = 'success' if total_anomaly_skus == 0 else 'danger'

            data['results'] = results
            data['summary'] = {
                'total_tables': len(get_monitoring_targets()),
                'total_anomaly_skus': total_anomaly_skus,
                'repeat_skus': total_repeat_skus,
                'new_skus': total_new_skus,
                'status': overall_status
            }

    except Exception as e:
        data['error'] = log_error(e)
        data['summary'] = {
            'total_tables': len(get_monitoring_targets()),
            'total_anomaly_skus': 0, 'repeat_skus': 0, 'new_skus': 0,
            'status': 'error'
        }

    return data


def get_sku_detail(target_date, days, retailer, filter_type, sort_by, sort_order, page, page_size):
    """특정 리테일러의 SKU별 이상치 상세 목록"""
    start_date = target_date - timedelta(days=days - 1)

    data = {
        'timestamp': datetime.now().isoformat(),
        'date': str(target_date),
        'days': days,
        'retailer': retailer,
        'filter': filter_type,
        'page': page,
        'page_size': page_size,
        'data': []
    }

    # 리테일러 정보 조회
    retailer_info = next((t for t in get_monitoring_targets() if t[1] == retailer), None)
    if not retailer_info:
        data['error'] = '유효하지 않은 리테일러입니다.'
        return data

    table_name = retailer_info[0]
    data['region'] = retailer_info[2]
    data['country'] = retailer_info[4].upper()
    data['table_name'] = table_name

    try:
        with ds_connection() as (conn, cursor):
            closed_dates = get_closed_dates(cursor, start_date, target_date)
            retailer_id_map = get_retailer_id_map(cursor)
            retailer_id = retailer_id_map.get(retailer)

            if not retailer_id:
                data['error'] = '리테일러 ID를 찾을 수 없습니다.'
                return data

            sku_map = build_sku_day_map(cursor, retailer_id, table_name, start_date, target_date, closed_dates)

        # SKU별 연속일수 계산 + 필터
        sku_list = []
        # 날짜 목록 생성 (프론트에서 day_map 표시용)
        date_list = []
        current = start_date
        while current <= target_date:
            date_list.append(str(current))
            current += timedelta(days=1)

        for sku, info in sku_map.items():
            consecutive = calc_consecutive_days(info['days'], target_date)
            if consecutive == 0:
                continue  # 기준일에 없는 SKU

            total_appearances = len(info['days'])
            sorted_dates = sorted(info['days'].keys())

            if filter_type == 'new' and consecutive != 1:
                continue
            if filter_type == 'repeat' and consecutive < 2:
                continue

            # day_map: 각 날짜에 이상치 여부
            day_map = {}
            for d_str in date_list:
                d = datetime.strptime(d_str, '%Y-%m-%d').date()
                day_map[d_str] = d in info['days']

            latest = info['latest'] or {}
            sku_list.append({
                'retailersku': sku,
                'consecutive_days': consecutive,
                'total_appearances': total_appearances,
                'first_seen': str(sorted_dates[0]),
                'last_seen': str(sorted_dates[-1]),
                'latest_title': latest.get('title', ''),
                'latest_retailprice': latest.get('retailprice', ''),
                'latest_imageurl': latest.get('imageurl', ''),
                'latest_producturl': latest.get('producturl', ''),
                'latest_cause': info['latest_cause'],
                'latest_memo': info['latest_memo'],
                'day_map': day_map
            })

        # 정렬
        reverse = sort_order == 'desc'
        if sort_by == 'retailersku':
            sku_list.sort(key=lambda x: x['retailersku'], reverse=reverse)
        elif sort_by == 'total_appearances':
            sku_list.sort(key=lambda x: x['total_appearances'], reverse=reverse)
        else:  # consecutive_days (기본)
            sku_list.sort(key=lambda x: x['consecutive_days'], reverse=reverse)

        # 페이징
        total_count = len(sku_list)
        offset = (page - 1) * page_size
        paged_list = sku_list[offset:offset + page_size]

        data['total_count'] = total_count
        data['total_pages'] = (total_count + page_size - 1) // page_size if total_count > 0 else 1
        data['dates'] = date_list
        data['data'] = paged_list

    except Exception as e:
        data['error'] = log_error(e)

    return data


def get_sku_history(target_date, days, retailer, retailersku):
    """단일 SKU의 날짜별 이상치 이력"""
    start_date = target_date - timedelta(days=days - 1)

    data = {
        'timestamp': datetime.now().isoformat(),
        'retailer': retailer,
        'retailersku': retailersku,
        'history': []
    }

    retailer_info = next((t for t in get_monitoring_targets() if t[1] == retailer), None)
    if not retailer_info:
        data['error'] = '유효하지 않은 리테일러입니다.'
        return data

    table_name = retailer_info[0]

    try:
        with ds_connection() as (conn, cursor):
            closed_dates = get_closed_dates(cursor, start_date, target_date)
            retailer_id_map = get_retailer_id_map(cursor)
            retailer_id = retailer_id_map.get(retailer)

            if not retailer_id:
                data['error'] = '리테일러 ID를 찾을 수 없습니다.'
                return data

            sku_map = build_sku_day_map(cursor, retailer_id, table_name, start_date, target_date, closed_dates)

        sku_info = sku_map.get(retailersku)
        if not sku_info:
            data['consecutive_days'] = 0
            data['total_appearances'] = 0
            return data

        consecutive = calc_consecutive_days(sku_info['days'], target_date)
        data['consecutive_days'] = consecutive
        data['total_appearances'] = len(sku_info['days'])

        # 날짜별 이력 구성
        history = []
        current = start_date
        while current <= target_date:
            entry = {
                'date': str(current),
                'source': 'closed' if current in closed_dates else 'realtime',
                'is_anomaly': current in sku_info['days']
            }
            if current in sku_info['days']:
                item = sku_info['days'][current]
                entry['title'] = item.get('title', '')
                entry['retailprice'] = item.get('retailprice', '')
                entry['ships_from'] = item.get('ships_from', '')
                entry['sold_by'] = item.get('sold_by', '')
                entry['imageurl'] = item.get('imageurl', '')
                entry['producturl'] = item.get('producturl', '')
                entry['cause'] = item.get('cause', '')
                entry['memo'] = item.get('memo', '')
                entry['screenshot_id'] = item.get('screenshot_id')
            history.append(entry)

        data['history'] = history

    except Exception as e:
        data['error'] = log_error(e)

    return data
