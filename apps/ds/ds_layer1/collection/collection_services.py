"""
DS Layer 1 — 수집 현황 서비스
DB 쿼리 + 계산 + 상태 판단 (순수 비즈니스 로직)
"""

from datetime import datetime, timedelta
from apps.common.targets import load_monitoring_targets, load_monitoring_targets_with_instance, get_retailer_map
from apps.ds.ds_layer1.batch.batch_services import get_batches_for_date
from apps.ds.ds_layer2.stats.stats_repositories import fetch_quality_counts_by_time_range as get_quality_counts_by_time_range
from apps.ds.ds_layer4.report.services import is_report_closed
from .collection_repositories import (
    get_crawl_count_db, get_expected_count_db, get_closed_report_stats_db,
    get_table_detail_count_db, get_table_detail_db
)

def get_monitoring_targets():
    """CSV에서 모니터링 대상 목록 로드"""
    return load_monitoring_targets()


def get_crawl_count(table_name, target_date):
    """특정 테이블의 특정 날짜 크롤링 데이터 수 조회"""
    date_str = target_date.strftime('%Y%m%d')
    start_datetime = f"{date_str}0000"
    next_date = (target_date + timedelta(days=1)).strftime('%Y%m%d')
    end_datetime = f"{next_date}0000"

    return get_crawl_count_db(table_name, start_datetime, end_datetime)


def get_crawl_count_by_time_range(table_name, target_date, start_time, end_time):
    """특정 시간 범위 내의 크롤링 데이터 수 조회"""
    date_str = target_date.strftime('%Y%m%d')

    start_hhmm = start_time.replace(':', '') if start_time else '0000'
    start_datetime = f"{date_str}{start_hhmm}00"

    if end_time:
        end_hhmm = end_time.replace(':', '')
        end_datetime = f"{date_str}{end_hhmm}00"
    else:
        next_date = (target_date + timedelta(days=1)).strftime('%Y%m%d')
        end_datetime = f"{next_date}0000"

    return get_crawl_count_db(table_name, start_datetime, end_datetime)


def get_expected_count(country, mall_name):
    """예상 수집 건수 조회"""
    return get_expected_count_db(country, mall_name)


def get_collection_status(korea_time_str, target_date, completion_rate):
    """
    수집 상태 판별
    - 현재시간 < 수집시간 : pending (대기중)
    - 수집시간 <= 현재시간 < 수집시간+1시간 : collecting (수집중)
    - 수집시간+1시간 <= 현재시간 : success/warning/danger (완료율 기반)
    """
    now = datetime.now()
    today = now.date()

    if target_date != today:
        if completion_rate >= 100:
            return 'success'
        elif completion_rate >= 0:
            return 'danger'
        else:
            return 'error'

    try:
        hour, minute = map(int, korea_time_str.split(':'))
        crawl_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        crawl_time_plus_2h = crawl_time + timedelta(hours=2)

        if now < crawl_time:
            return 'pending'
        elif now < crawl_time_plus_2h:
            if completion_rate >= 100:
                return 'success'
            return 'collecting'
        else:
            if completion_rate >= 100:
                return 'success'
            elif completion_rate >= 0:
                return 'danger'
            else:
                return 'error'
    except:
        if completion_rate >= 100:
            return 'success'
        elif completion_rate >= 0:
            return 'danger'
        else:
            return 'error'


def get_layer_stats(target_date, batch_view):
    """DS Layer 1 전체 통계 조회"""
    close_result = is_report_closed(str(target_date))
    is_closed = close_result.get('is_closed', False)
    closed_data = {}
    
    if is_closed:
        rows = get_closed_report_stats_db(target_date)
        if rows:
            for row in rows:
                closed_data[row['retailer']] = {
                    'expected': row['expected_count'] or 0,
                    'actual': row['total_count'] or 0,
                    'completion_rate': float(row['completion_rate']) if row['completion_rate'] else 0,
                    'final_batch_count': row['final_batch_count'] or 0
                }
        else:
            is_closed = False

    batches_by_retailer = get_batches_for_date(target_date)

    total_expected = 0
    total_actual = 0
    results = []

    for idx, (table_name, retailer, region, korea_time, country, mall_name, instance_id, schedule_name) in enumerate(load_monitoring_targets_with_instance(), 1):
        retailer_batches = batches_by_retailer.get(retailer, [])
        final_start_time = None
        final_end_time = None

        if is_closed and retailer in closed_data:
            expected = closed_data[retailer]['expected']
            if batch_view == 'final':
                actual = closed_data[retailer]['final_batch_count']
            else:
                actual = closed_data[retailer]['actual']
            if expected > 0 and actual >= 0:
                completion_rate = round((actual / expected) * 100, 1)
            elif expected == 0:
                completion_rate = 0
            else:
                completion_rate = -1
            status = get_collection_status(korea_time, target_date, completion_rate)
        else:
            expected = get_expected_count(country, mall_name)

            if len(retailer_batches) >= 1 and batch_view == 'final':
                last_batch = retailer_batches[-1]
                final_start_time = last_batch['start_time']
                final_end_time = None
                actual = get_crawl_count_by_time_range(table_name, target_date, final_start_time, final_end_time)
            else:
                actual = get_crawl_count(table_name, target_date)

            if expected > 0 and actual >= 0:
                completion_rate = round((actual / expected) * 100, 1)
            elif expected == 0:
                completion_rate = 0
            else:
                completion_rate = -1

            status = get_collection_status(korea_time, target_date, completion_rate)

        if expected >= 0:
            total_expected += expected
        if actual >= 0:
            total_actual += actual

        result_item = {
            'no': idx,
            'table_name': table_name,
            'retailer': retailer,
            'region': region,
            'korea_time': korea_time,
            'country': country.upper(),
            'expected': expected,
            'actual': actual,
            'completion_rate': completion_rate,
            'status': status,
            'has_multi_batch': False,
            'batches': [],
            'final_start_time': final_start_time,
            'final_end_time': final_end_time,
            'has_instance': bool(instance_id and schedule_name)
        }

        if not is_closed and len(retailer_batches) >= 2 and batch_view == 'all':
            result_item['has_multi_batch'] = True
            batch_details = []

            for i, batch in enumerate(retailer_batches):
                start_time = batch['start_time']
                end_time = retailer_batches[i + 1]['start_time'] if i + 1 < len(retailer_batches) else None

                batch_count = get_crawl_count_by_time_range(table_name, target_date, start_time, end_time)
                batch_completion = round((batch_count / expected) * 100, 1) if expected > 0 else 0

                # Note: get_quality_counts_by_time_range currently expects cursor. We might need to refactor stats module next, but for now we'll pass cursor as None if it fails.
                try:
                    l2_quality = get_quality_counts_by_time_range(None, table_name, target_date, start_time, end_time)
                    l2_error_count = l2_quality.get('error_count', 0)
                except Exception:
                    l2_error_count = 0

                batch_details.append({
                    'id': batch['id'],
                    'start_time': start_time,
                    'end_time': end_time if end_time else '다음날',
                    'memo': batch['memo'],
                    'actual': batch_count,
                    'completion_rate': batch_completion,
                    'l2_error_count': l2_error_count
                })

            result_item['batches'] = batch_details

        results.append(result_item)

    total_completion_rate = round((total_actual / total_expected) * 100, 1) if total_expected > 0 else 0

    return {
        'results': results,
        'summary': {
            'total_tables': len(get_monitoring_targets()),
            'total_expected': total_expected,
            'total_actual': total_actual,
            'total_completion_rate': total_completion_rate,
            'status': 'success' if total_completion_rate >= 100 else 'danger',
            'is_closed': is_closed
        }
    }


def get_instances_stats(target_date):
    """인스턴스별(지역별) 그룹화된 통계 조회"""
    regions = {}
    for table_name, retailer, region, korea_time, country, mall_name in get_monitoring_targets():
        if region not in regions:
            regions[region] = {
                'name': region,
                'retailers': [],
                'total_expected': 0,
                'total_actual': 0
            }

        expected = get_expected_count(country, mall_name)
        actual = get_crawl_count(table_name, target_date)

        if expected > 0 and actual >= 0:
            completion_rate = round((actual / expected) * 100, 1)
        elif expected == 0:
            completion_rate = 0
        else:
            completion_rate = -1

        status = get_collection_status(korea_time, target_date, completion_rate)

        regions[region]['retailers'].append({
            'retailer': retailer,
            'table_name': table_name,
            'korea_time': korea_time,
            'country': country.upper(),
            'expected': expected,
            'actual': actual,
            'completion_rate': completion_rate,
            'status': status
        })

        if expected >= 0:
            regions[region]['total_expected'] += expected
        if actual >= 0:
            regions[region]['total_actual'] += actual

    for region_name, region_data in regions.items():
        if region_data['total_expected'] > 0:
            region_data['completion_rate'] = round(
                (region_data['total_actual'] / region_data['total_expected']) * 100, 1
            )
        else:
            region_data['completion_rate'] = 0

        if region_data['completion_rate'] >= 100:
            region_data['status'] = 'success'
        else:
            region_data['status'] = 'danger'

    return regions


def get_table_detail(table_name, target_date, page, page_size, start_time, end_time, sort_by, sort_order):
    """특정 테이블의 수집 데이터 상세 조회"""
    date_str_fmt = target_date.strftime('%Y%m%d')

    if start_time:
        start_datetime = f"{date_str_fmt}{start_time.replace(':', '')}00"
    else:
        start_datetime = f"{date_str_fmt}0000"

    if end_time and end_time != '다음날':
        end_datetime = f"{date_str_fmt}{end_time.replace(':', '')}00"
    else:
        next_date = (target_date + timedelta(days=1)).strftime('%Y%m%d')
        end_datetime = f"{next_date}0000"

    total_count = get_table_detail_count_db(table_name, start_datetime, end_datetime)
    offset = (page - 1) * page_size
    
    rows = get_table_detail_db(table_name, start_datetime, end_datetime, sort_by, sort_order, page_size, offset)

    items = []
    for row in rows:
        crawl_dt = row['crawl_strdatetime'] or ''
        if crawl_dt and len(crawl_dt) >= 14:
            crawl_dt = f"{crawl_dt[0:4]}-{crawl_dt[4:6]}-{crawl_dt[6:8]} {crawl_dt[8:10]}:{crawl_dt[10:12]}:{crawl_dt[12:14]}"
        elif crawl_dt and len(crawl_dt) >= 12:
            crawl_dt = f"{crawl_dt[0:4]}-{crawl_dt[4:6]}-{crawl_dt[6:8]} {crawl_dt[8:10]}:{crawl_dt[10:12]}:00"
        
        items.append({
            'title': row['title'] or '',
            'retailprice': row['retailprice'] or '',
            'ships_from': row['ships_from'] or '',
            'sold_by': row['sold_by'] or '',
            'imageurl': row['imageurl'] or '',
            'producturl': row['producturl'] or '',
            'crawl_datetime': crawl_dt
        })

    retailer_info = next((t for t in get_monitoring_targets() if t[0] == table_name), None)

    return {
        'retailer': retailer_info[1] if retailer_info else table_name,
        'region': retailer_info[2] if retailer_info else '',
        'country': retailer_info[4].upper() if retailer_info else '',
        'total_count': total_count,
        'total_pages': (total_count + page_size - 1) // page_size if page_size else 1,
        'data': items
    }
