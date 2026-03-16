"""
DS Layer 1 — 수집 현황 서비스
DB 쿼리 + 계산 + 상태 판단 (순수 비즈니스 로직)
"""

from datetime import datetime, timedelta
from apps.common.targets import load_monitoring_targets, load_monitoring_targets_with_instance, get_retailer_map
from apps.ds.ds_layer1.batch.services import get_batches_for_date
from apps.ds.ds_layer2.stats.services import get_quality_counts_by_time_range
from apps.ds.ds_layer4.report.services import is_report_closed


def get_monitoring_targets():
    """CSV에서 모니터링 대상 목록 로드"""
    return load_monitoring_targets()


def get_crawl_count(cursor, table_name, target_date):
    """특정 테이블의 특정 날짜 크롤링 데이터 수 조회"""
    date_str = target_date.strftime('%Y%m%d')
    start_datetime = f"{date_str}0000"
    next_date = (target_date + timedelta(days=1)).strftime('%Y%m%d')
    end_datetime = f"{next_date}0000"

    query = f"""
        SELECT COUNT(*) as cnt FROM (
            SELECT DISTINCT * FROM samsung_ds_retail_com.{table_name}
            WHERE crawl_strdatetime >= %s AND crawl_strdatetime < %s
        ) A
    """

    try:
        cursor.execute(query, (start_datetime, end_datetime))
        result = cursor.fetchone()
        return result[0] if result else 0
    except Exception as e:
        return -1


def get_crawl_count_by_time_range(cursor, table_name, target_date, start_time, end_time):
    """특정 시간 범위 내의 크롤링 데이터 수 조회
    start_time, end_time: 'HH:MM' 형식
    end_time이 None이면 다음날 00:00까지
    """
    date_str = target_date.strftime('%Y%m%d')

    start_hhmm = start_time.replace(':', '') if start_time else '0000'
    start_datetime = f"{date_str}{start_hhmm}00"

    if end_time:
        end_hhmm = end_time.replace(':', '')
        end_datetime = f"{date_str}{end_hhmm}00"
    else:
        next_date = (target_date + timedelta(days=1)).strftime('%Y%m%d')
        end_datetime = f"{next_date}0000"

    query = f"""
        SELECT COUNT(*) as cnt FROM (
            SELECT DISTINCT * FROM samsung_ds_retail_com.{table_name}
            WHERE crawl_strdatetime >= %s AND crawl_strdatetime < %s
        ) A
    """

    try:
        cursor.execute(query, (start_datetime, end_datetime))
        result = cursor.fetchone()
        return result[0] if result else 0
    except Exception as e:
        return -1


def get_expected_count(cursor, country, mall_name):
    """예상 수집 건수 조회 (samsung_price_tracking_list에서 is_active=1인 항목 수)"""
    query = """
        SELECT COUNT(*) as cnt FROM samsung_ds_retail_com.samsung_price_tracking_list
        WHERE country = %s AND mall_name = %s AND is_active = 1
    """

    try:
        cursor.execute(query, (country, mall_name))
        result = cursor.fetchone()
        count = result[0] if result else 0

        return count
    except Exception as e:
        return -1


def get_collection_status(korea_time_str, target_date, completion_rate):
    """
    수집 상태 판별
    - 현재시간 < 수집시간 : pending (대기중)
    - 수집시간 <= 현재시간 < 수집시간+1시간 : collecting (수집중)
    - 수집시간+1시간 <= 현재시간 : success/warning/danger (완료율 기반)
    """
    now = datetime.now()
    today = now.date()

    # 조회 날짜가 오늘이 아니면 완료율 기반 판단
    if target_date != today:
        if completion_rate >= 100:
            return 'success'
        elif completion_rate >= 0:
            return 'danger'
        else:
            return 'error'

    # 오늘 날짜인 경우 시간 비교
    try:
        hour, minute = map(int, korea_time_str.split(':'))
        crawl_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        crawl_time_plus_2h = crawl_time + timedelta(hours=2)

        if now < crawl_time:
            return 'pending'  # 대기중
        elif now < crawl_time_plus_2h:
            # 수집중이지만 100% 달성했으면 결과 표시
            if completion_rate >= 100:
                return 'success'
            return 'collecting'  # 수집중
        else:
            # 수집 완료 시간 지남 - 완료율 기반 판단
            if completion_rate >= 100:
                return 'success'
            elif completion_rate >= 0:
                return 'danger'
            else:
                return 'error'
    except:
        # 시간 파싱 실패 시 완료율 기반 판단
        if completion_rate >= 100:
            return 'success'
        elif completion_rate >= 0:
            return 'danger'
        else:
            return 'error'


def get_layer_stats(cursor, target_date, batch_view, conn=None):
    """DS Layer 1 전체 통계 조회"""
    # 마감 여부 확인 → 마감된 날짜는 현황 테이블 스냅샷 사용
    close_result = is_report_closed(str(target_date), existing=(conn, cursor) if conn else None)
    is_closed = close_result.get('is_closed', False)
    closed_data = {}
    if is_closed:
        try:
            cursor.execute("""
                SELECT t.retailer, r.expected_count, r.total_count, r.completion_rate, r.final_batch_count
                FROM ssd_crawl_db.ds_monitoring_report_daily r
                JOIN ssd_crawl_db.ds_monitoring_targets t ON r.retailer_id = t.retailer_id
                WHERE r.crawl_date = %s AND r.is_del = 0
            """, (target_date,))
            for row in cursor.fetchall():
                closed_data[row[0]] = {
                    'expected': row[1] or 0,
                    'actual': row[2] or 0,
                    'completion_rate': float(row[3]) if row[3] else 0,
                    'final_batch_count': row[4] or 0
                }
        except:
            is_closed = False

    # 배치 정보 로드
    batches_by_retailer = get_batches_for_date(target_date)

    total_expected = 0
    total_actual = 0
    results = []

    for idx, (table_name, retailer, region, korea_time, country, mall_name, instance_id, schedule_name) in enumerate(load_monitoring_targets_with_instance(), 1):
        retailer_batches = batches_by_retailer.get(retailer, [])
        final_start_time = None
        final_end_time = None

        # 마감된 날짜 + 현황 데이터 있음 → 스냅샷 사용 (실시간 쿼리 생략)
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
            # 미마감 → 실시간 쿼리 (기존 로직)
            expected = get_expected_count(cursor, country, mall_name)

            if len(retailer_batches) >= 1 and batch_view == 'final':
                last_batch = retailer_batches[-1]
                final_start_time = last_batch['start_time']
                final_end_time = None
                actual = get_crawl_count_by_time_range(cursor, table_name, target_date, final_start_time, final_end_time)
            else:
                actual = get_crawl_count(cursor, table_name, target_date)

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

        # 배치 정보 추가 (미마감 + 2개 이상 + 'all' 뷰인 경우)
        if not is_closed and len(retailer_batches) >= 2 and batch_view == 'all':
            result_item['has_multi_batch'] = True
            batch_details = []

            for i, batch in enumerate(retailer_batches):
                start_time = batch['start_time']
                end_time = retailer_batches[i + 1]['start_time'] if i + 1 < len(retailer_batches) else None

                batch_count = get_crawl_count_by_time_range(cursor, table_name, target_date, start_time, end_time)
                batch_completion = round((batch_count / expected) * 100, 1) if expected > 0 else 0

                l2_quality = get_quality_counts_by_time_range(cursor, table_name, target_date, start_time, end_time)
                l2_error_count = l2_quality.get('error_count', 0)

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

    # 전체 완료율
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


def get_instances_stats(cursor, target_date):
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

        expected = get_expected_count(cursor, country, mall_name)
        actual = get_crawl_count(cursor, table_name, target_date)

        # 완료율 계산
        if expected > 0 and actual >= 0:
            completion_rate = round((actual / expected) * 100, 1)
        elif expected == 0:
            completion_rate = 0
        else:
            completion_rate = -1

        # 상태 판단 (시간 기반)
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

    # 지역별 완료율 계산
    for region_name, region_data in regions.items():
        if region_data['total_expected'] > 0:
            region_data['completion_rate'] = round(
                (region_data['total_actual'] / region_data['total_expected']) * 100, 1
            )
        else:
            region_data['completion_rate'] = 0

        # 지역 상태
        if region_data['completion_rate'] >= 100:
            region_data['status'] = 'success'
        else:
            region_data['status'] = 'danger'

    return regions


def get_table_detail(cursor, table_name, target_date, page, page_size, start_time, end_time, sort_by, sort_order):
    """특정 테이블의 수집 데이터 상세 조회"""
    date_str_fmt = target_date.strftime('%Y%m%d')

    # 시간 범위가 지정된 경우 해당 범위로 필터링
    if start_time:
        start_datetime = f"{date_str_fmt}{start_time.replace(':', '')}00"
    else:
        start_datetime = f"{date_str_fmt}0000"

    if end_time and end_time != '다음날':
        end_datetime = f"{date_str_fmt}{end_time.replace(':', '')}00"
    else:
        next_date = (target_date + timedelta(days=1)).strftime('%Y%m%d')
        end_datetime = f"{next_date}0000"

    # 전체 건수 조회
    count_query = f"""
        SELECT COUNT(*) FROM (
            SELECT DISTINCT * FROM samsung_ds_retail_com.{table_name}
            WHERE crawl_strdatetime >= %s AND crawl_strdatetime < %s
        ) A
    """
    cursor.execute(count_query, (start_datetime, end_datetime))
    total_count = cursor.fetchone()[0]

    # 페이징된 데이터 조회
    offset = (page - 1) * page_size

    # 정렬 컬럼 검증 (SQL Injection 방지)
    valid_sort_columns = ['crawl_strdatetime', 'title', 'retailprice', 'ships_from', 'sold_by']
    if sort_by not in valid_sort_columns:
        sort_by = 'crawl_strdatetime'
    sort_direction = 'DESC' if sort_order.lower() == 'desc' else 'ASC'

    query = f"""
        SELECT title, retailprice, ships_from, sold_by, imageurl, producturl, crawl_strdatetime
        FROM (
            SELECT DISTINCT * FROM samsung_ds_retail_com.{table_name}
            WHERE crawl_strdatetime >= %s AND crawl_strdatetime < %s
        ) A
        ORDER BY {sort_by} {sort_direction}, title
        LIMIT %s OFFSET %s
    """

    cursor.execute(query, (start_datetime, end_datetime, page_size, offset))
    rows = cursor.fetchall()

    items = []
    for row in rows:
        # crawl_strdatetime 포맷팅 (YYYYMMDDHHMMSS... -> YYYY-MM-DD HH:MM:SS)
        crawl_dt = row[6] or ''
        if crawl_dt and len(crawl_dt) >= 14:
            crawl_dt = f"{crawl_dt[0:4]}-{crawl_dt[4:6]}-{crawl_dt[6:8]} {crawl_dt[8:10]}:{crawl_dt[10:12]}:{crawl_dt[12:14]}"
        elif crawl_dt and len(crawl_dt) >= 12:
            crawl_dt = f"{crawl_dt[0:4]}-{crawl_dt[4:6]}-{crawl_dt[6:8]} {crawl_dt[8:10]}:{crawl_dt[10:12]}:00"
        items.append({
            'title': row[0] or '',
            'retailprice': row[1] or '',
            'ships_from': row[2] or '',
            'sold_by': row[3] or '',
            'imageurl': row[4] or '',
            'producturl': row[5] or '',
            'crawl_datetime': crawl_dt
        })

    # 리테일러 정보 찾기
    retailer_info = next((t for t in get_monitoring_targets() if t[0] == table_name), None)

    return {
        'retailer': retailer_info[1] if retailer_info else table_name,
        'region': retailer_info[2] if retailer_info else '',
        'country': retailer_info[4].upper() if retailer_info else '',
        'total_count': total_count,
        'total_pages': (total_count + page_size - 1) // page_size,
        'data': items
    }
