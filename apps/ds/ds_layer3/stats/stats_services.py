"""
DS Layer 3 Stats Service: SKU 이상치 반복 패턴 분석 비즈니스 로직
"""
from datetime import datetime, timedelta
from apps.common.db import ds_connection
from apps.common.response import log_error
from . import stats_repositories

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
            closed_dates = stats_repositories.get_closed_dates(cursor, start_date, target_date)
            retailer_id_map = stats_repositories.get_retailer_id_map(cursor)

            results = []
            total_anomaly_skus = 0
            total_repeat_skus = 0
            total_new_skus = 0

            for idx, (table_name, retailer, region, korea_time, country, mall_name) in enumerate(stats_repositories.get_monitoring_targets(), 1):
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
                    sku_map = stats_repositories.build_sku_day_map(cursor, retailer_id, table_name, start_date, target_date, closed_dates)

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
                'total_tables': len(stats_repositories.get_monitoring_targets()),
                'total_anomaly_skus': total_anomaly_skus,
                'repeat_skus': total_repeat_skus,
                'new_skus': total_new_skus,
                'status': overall_status
            }

    except Exception as e:
        data['error'] = log_error(e)
        data['summary'] = {
            'total_tables': len(stats_repositories.get_monitoring_targets()),
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
    retailer_info = next((t for t in stats_repositories.get_monitoring_targets() if t[1] == retailer), None)
    if not retailer_info:
        data['error'] = '유효하지 않은 리테일러입니다.'
        return data

    table_name = retailer_info[0]
    data['region'] = retailer_info[2]
    data['country'] = retailer_info[4].upper()
    data['table_name'] = table_name

    try:
        with ds_connection() as (conn, cursor):
            closed_dates = stats_repositories.get_closed_dates(cursor, start_date, target_date)
            retailer_id_map = stats_repositories.get_retailer_id_map(cursor)
            retailer_id = retailer_id_map.get(retailer)

            if not retailer_id:
                data['error'] = '리테일러 ID를 찾을 수 없습니다.'
                return data

            sku_map = stats_repositories.build_sku_day_map(cursor, retailer_id, table_name, start_date, target_date, closed_dates)

        # SKU별 연속일수 계산 + 필터
        sku_list = []
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

    retailer_info = next((t for t in stats_repositories.get_monitoring_targets() if t[1] == retailer), None)
    if not retailer_info:
        data['error'] = '유효하지 않은 리테일러입니다.'
        return data

    table_name = retailer_info[0]

    try:
        with ds_connection() as (conn, cursor):
            closed_dates = stats_repositories.get_closed_dates(cursor, start_date, target_date)
            retailer_id_map = stats_repositories.get_retailer_id_map(cursor)
            retailer_id = retailer_id_map.get(retailer)

            if not retailer_id:
                data['error'] = '리테일러 ID를 찾을 수 없습니다.'
                return data

            sku_map = stats_repositories.build_sku_day_map(cursor, retailer_id, table_name, start_date, target_date, closed_dates)

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
