"""
DS Layer 1 API: 기본 통계 검수
인스턴스별/지역별 수집 현황 API
파일서버 용량 조회 API
"""

from django.http import JsonResponse
from datetime import datetime, timedelta, date
from apps.common.db import get_ds_connection
from apps.common.response import safe_error, log_error
from config.config import FILE_SERVER_CONFIG, SSM_CONFIG
from apps.common.targets import load_monitoring_targets, load_monitoring_targets_with_local_time, load_monitoring_targets_with_instance, get_retailer_map, format_time
import json
import re
import boto3
import pytz
from apps.ds.ds_layer2.api.views import get_quality_counts_by_time_range
import paramiko


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
    start_datetime = f"{date_str}{start_time.replace(':', '')}00"

    if end_time:
        end_datetime = f"{date_str}{end_time.replace(':', '')}00"
    else:
        # 다음날 00:00
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


def get_batches_for_date(target_date):
    """특정 날짜의 배치 목록을 리테일러별로 그룹화하여 반환"""
    batches_by_retailer = {}

    try:
        conn = get_ds_connection()
        cursor = conn.cursor()

        query = """
            SELECT id, retailer, start_time, memo
            FROM ssd_crawl_db.ds_collection_batch_log
            WHERE date = %s
            ORDER BY retailer, start_time
        """
        cursor.execute(query, (target_date,))
        rows = cursor.fetchall()

        for row in rows:
            retailer = row[1]
            if retailer not in batches_by_retailer:
                batches_by_retailer[retailer] = []

            batches_by_retailer[retailer].append({
                'id': row[0],
                'start_time': format_time(row[2]) if row[2] else '00:00',
                'memo': row[3]
            })

        cursor.close()
        conn.close()
    except Exception as e:
        print(f"Error loading batches: {e}")

    return batches_by_retailer


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


def layer_stats(request):
    """DS Layer 1 전체 통계 API"""
    date_str = request.GET.get('date')
    batch_view = request.GET.get('batch_view', 'final')  # 'final' or 'all'

    if date_str:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    else:
        target_date = (datetime.now() - timedelta(days=1)).date()

    data = {
        'timestamp': datetime.now().isoformat(),
        'date': str(target_date),
        'layer': 1,
        'data_source': 'ds',
        'results': [],
        'summary': {}
    }

    try:
        conn = get_ds_connection()
        cursor = conn.cursor()

        # 마감 여부 확인 → 마감된 날짜는 현황 테이블 스냅샷 사용
        is_closed = False
        closed_data = {}
        try:
            cursor.execute("""
                SELECT is_closed FROM ssd_crawl_db.ds_monitoring_report_close
                WHERE crawl_date = %s
            """, (target_date,))
            close_row = cursor.fetchone()
            if close_row and close_row[0] == 1:
                is_closed = True
                cursor.execute("""
                    SELECT t.retailer, r.expected_count, r.total_count, r.completion_rate
                    FROM ssd_crawl_db.ds_monitoring_report_daily r
                    JOIN ssd_crawl_db.ds_monitoring_targets t ON r.retailer_id = t.retailer_id
                    WHERE r.crawl_date = %s AND r.is_del = 0
                """, (target_date,))
                for row in cursor.fetchall():
                    closed_data[row[0]] = {
                        'expected': row[1] or 0,
                        'actual': row[2] or 0,
                        'completion_rate': float(row[3]) if row[3] else 0
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
                actual = closed_data[retailer]['actual']
                completion_rate = closed_data[retailer]['completion_rate']
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

        cursor.close()
        conn.close()

        data['results'] = results
        data['summary'] = {
            'total_tables': len(get_monitoring_targets()),
            'total_expected': total_expected,
            'total_actual': total_actual,
            'total_completion_rate': total_completion_rate,
            'status': 'success' if total_completion_rate >= 100 else 'danger',
            'is_closed': is_closed
        }

    except Exception as e:
        data['error'] = log_error(e)
        data['summary'] = {
            'total_tables': len(get_monitoring_targets()),
            'total_expected': 0,
            'total_actual': 0,
            'total_completion_rate': 0,
            'status': 'error'
        }

    return JsonResponse(data)


def instances_stats(request):
    """인스턴스별(지역별) 그룹화된 통계 API"""
    date_str = request.GET.get('date')

    if date_str:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    else:
        target_date = (datetime.now() - timedelta(days=1)).date()

    data = {
        'timestamp': datetime.now().isoformat(),
        'date': str(target_date),
        'regions': {}
    }

    try:
        conn = get_ds_connection()
        cursor = conn.cursor()

        # 지역별로 그룹화
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

        cursor.close()
        conn.close()

        data['regions'] = regions

    except Exception as e:
        data['error'] = log_error(e)

    return JsonResponse(data)


def table_detail(request):
    """특정 테이블의 수집 데이터 상세 조회 API"""
    date_str = request.GET.get('date')
    table_name = request.GET.get('table')
    try:
        page = max(1, int(request.GET.get('page', 1)))
        page_size = min(int(request.GET.get('page_size', 50)), 200)
    except (ValueError, TypeError):
        return JsonResponse({'error': '잘못된 페이지 파라미터'}, status=400)
    # 배치별 시간 범위 파라미터 (HH:MM 형식)
    start_time = request.GET.get('start_time')
    end_time = request.GET.get('end_time')
    # 정렬 파라미터
    sort_by = request.GET.get('sort_by', 'crawl_strdatetime')
    sort_order = request.GET.get('sort_order', 'asc')

    if not table_name:
        return JsonResponse({'error': '테이블명을 입력하세요.'})

    # 테이블명 검증
    valid_tables = [t[0] for t in get_monitoring_targets()]
    if table_name not in valid_tables:
        return JsonResponse({'error': '유효하지 않은 테이블명입니다.'})

    if date_str:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    else:
        target_date = (datetime.now() - timedelta(days=1)).date()

    data = {
        'timestamp': datetime.now().isoformat(),
        'date': str(target_date),
        'table': table_name,
        'page': page,
        'page_size': page_size,
        'start_time': start_time,
        'end_time': end_time,
        'sort_by': sort_by,
        'sort_order': sort_order,
        'data': []
    }

    try:
        conn = get_ds_connection()
        cursor = conn.cursor()

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
            # crawl_strdatetime 포맷 변환 (YYYYMMDDHHMM00 -> YYYY-MM-DD HH:MM.000)
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

        cursor.close()
        conn.close()

        # 리테일러 정보 찾기
        retailer_info = next((t for t in get_monitoring_targets() if t[0] == table_name), None)

        data['retailer'] = retailer_info[1] if retailer_info else table_name
        data['region'] = retailer_info[2] if retailer_info else ''
        data['country'] = retailer_info[4].upper() if retailer_info else ''
        data['total_count'] = total_count
        data['total_pages'] = (total_count + page_size - 1) // page_size
        data['data'] = items

    except Exception as e:
        data['error'] = log_error(e)

    return JsonResponse(data)





def get_directory_size(sftp, path):
    """SFTP로 디렉토리 용량 조회 (바이트)"""
    total_size = 0
    try:
        for entry in sftp.listdir_attr(path):
            entry_path = f"{path}/{entry.filename}"
            if entry.st_mode & 0o40000:  # 디렉토리인 경우
                total_size += get_directory_size(sftp, entry_path)
            else:
                total_size += entry.st_size
    except Exception:
        pass
    return total_size


def format_size(size_bytes):
    """바이트를 읽기 쉬운 형식으로 변환"""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


def batch_list(request):
    """배치 로그 목록 조회 API (해당 날짜)"""
    date_str = request.GET.get('date')

    if date_str:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    else:
        target_date = (datetime.now() - timedelta(days=1)).date()

    data = {
        'timestamp': datetime.now().isoformat(),
        'date': str(target_date),
        'batches': []
    }

    try:
        conn = get_ds_connection()
        cursor = conn.cursor()

        # 해당 날짜의 배치 로그 조회
        query = """
            SELECT id, date, retailer, start_time, memo, created_at
            FROM ssd_crawl_db.ds_collection_batch_log
            WHERE date = %s
            ORDER BY retailer, start_time
        """
        cursor.execute(query, (target_date,))
        rows = cursor.fetchall()

        batches = []
        for row in rows:
            batches.append({
                'id': row[0],
                'date': str(row[1]),
                'retailer': row[2],
                'start_time': format_time(row[3]) if row[3] else None,
                'memo': row[4],
                'created_at': row[5].isoformat() if row[5] else None
            })

        cursor.close()
        conn.close()

        data['batches'] = batches

    except Exception as e:
        data['error'] = log_error(e)

    return JsonResponse(data)


def batch_init(request):
    """배치 로그 초기화 API (해당 날짜에 기본 배치 생성)"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST 요청만 허용됩니다.'}, status=405)

    import json
    try:
        body = json.loads(request.body)
        date_str = body.get('date')
    except:
        date_str = request.POST.get('date')

    if not date_str:
        return JsonResponse({'error': '날짜를 입력하세요.'}, status=400)

    try:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        return JsonResponse({'error': '날짜 형식이 올바르지 않습니다.'}, status=400)

    try:
        conn = get_ds_connection()
        cursor = conn.cursor()

        # 이미 해당 날짜에 배치가 있는지 확인
        check_query = """
            SELECT COUNT(*) FROM ssd_crawl_db.ds_collection_batch_log
            WHERE date = %s
        """
        cursor.execute(check_query, (target_date,))
        count = cursor.fetchone()[0]

        if count > 0:
            cursor.close()
            conn.close()
            return JsonResponse({'message': '이미 배치가 존재합니다.', 'created': 0})

        # 모니터링 대상 목록에서 기본 배치 생성 (local_time 사용)
        targets = load_monitoring_targets_with_local_time()
        insert_query = """
            INSERT INTO ssd_crawl_db.ds_collection_batch_log
            (date, retailer, start_time, memo)
            VALUES (%s, %s, %s, %s)
        """

        created_count = 0
        for table_name, retailer, region, korea_time, local_time, country, mall_name in targets:
            cursor.execute(insert_query, (target_date, retailer, local_time + ':00', None))
            created_count += 1

        conn.commit()
        cursor.close()
        conn.close()

        return JsonResponse({'message': f'{created_count}개 배치가 생성되었습니다.', 'created': created_count})

    except Exception as e:
        return safe_error(e)


def batch_create(request):
    """배치 로그 추가 API"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST 요청만 허용됩니다.'}, status=405)

    import json
    try:
        body = json.loads(request.body)
    except:
        return JsonResponse({'error': '잘못된 요청 형식입니다.'}, status=400)

    date_str = body.get('date')
    retailer = body.get('retailer')
    start_time = body.get('start_time')
    memo = body.get('memo', '')

    if not date_str or not retailer or not start_time:
        return JsonResponse({'error': '필수 필드가 누락되었습니다.'}, status=400)

    try:
        conn = get_ds_connection()
        cursor = conn.cursor()

        insert_query = """
            INSERT INTO ssd_crawl_db.ds_collection_batch_log
            (date, retailer, start_time, memo)
            VALUES (%s, %s, %s, %s)
        """
        cursor.execute(insert_query, (date_str, retailer, start_time, memo))
        conn.commit()

        # 새로 생성된 ID 가져오기
        cursor.execute("SELECT LAST_INSERT_ID()")
        new_id = cursor.fetchone()[0]

        cursor.close()
        conn.close()

        return JsonResponse({'message': '배치가 추가되었습니다.', 'id': new_id})

    except Exception as e:
        return safe_error(e)


def batch_update(request):
    """배치 로그 수정 API"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST 요청만 허용됩니다.'}, status=405)

    import json
    try:
        body = json.loads(request.body)
    except:
        return JsonResponse({'error': '잘못된 요청 형식입니다.'}, status=400)

    batch_id = body.get('id')
    start_time = body.get('start_time')
    memo = body.get('memo')

    if not batch_id:
        return JsonResponse({'error': 'ID가 필요합니다.'}, status=400)

    try:
        conn = get_ds_connection()
        cursor = conn.cursor()

        # 업데이트할 필드 동적 구성
        updates = []
        params = []

        if start_time is not None:
            updates.append("start_time = %s")
            params.append(start_time)

        if memo is not None:
            updates.append("memo = %s")
            params.append(memo)

        if not updates:
            return JsonResponse({'error': '수정할 필드가 없습니다.'}, status=400)

        params.append(batch_id)

        update_query = f"""
            UPDATE ssd_crawl_db.ds_collection_batch_log
            SET {', '.join(updates)}
            WHERE id = %s
        """
        cursor.execute(update_query, params)
        conn.commit()

        affected = cursor.rowcount
        cursor.close()
        conn.close()

        if affected == 0:
            return JsonResponse({'error': '해당 배치를 찾을 수 없습니다.'}, status=404)

        return JsonResponse({'message': '배치가 수정되었습니다.'})

    except Exception as e:
        return safe_error(e)


def batch_delete(request):
    """배치 로그 삭제 API"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST 요청만 허용됩니다.'}, status=405)

    import json
    try:
        body = json.loads(request.body)
    except:
        return JsonResponse({'error': '잘못된 요청 형식입니다.'}, status=400)

    batch_id = body.get('id')

    if not batch_id:
        return JsonResponse({'error': 'ID가 필요합니다.'}, status=400)

    try:
        conn = get_ds_connection()
        cursor = conn.cursor()

        delete_query = """
            DELETE FROM ssd_crawl_db.ds_collection_batch_log
            WHERE id = %s
        """
        cursor.execute(delete_query, (batch_id,))
        conn.commit()

        affected = cursor.rowcount
        cursor.close()
        conn.close()

        if affected == 0:
            return JsonResponse({'error': '해당 배치를 찾을 수 없습니다.'}, status=404)

        return JsonResponse({'message': '배치가 삭제되었습니다.'})

    except Exception as e:
        return safe_error(e)


def fileserver_stats(request):
    """파일서버 날짜별 용량 조회 API - SFTP 직접 조회"""
    date_str = request.GET.get('date')

    if date_str:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    else:
        target_date = (datetime.now() - timedelta(days=1)).date()

    date_folder = target_date.strftime('%Y%m%d')

    data = {
        'timestamp': datetime.now().isoformat(),
        'date': str(target_date),
        'date_folder': date_folder,
        'countries': [],
        'summary': {}
    }

    try:
        # 파일서버 연결
        transport = paramiko.Transport((FILE_SERVER_CONFIG['host'], FILE_SERVER_CONFIG['port']))
        transport.connect(
            username=FILE_SERVER_CONFIG['username'],
            password=FILE_SERVER_CONFIG['password']
        )
        sftp = paramiko.SFTPClient.from_transport(transport)

        base_path = FILE_SERVER_CONFIG['upload_path']
        total_size = 0
        total_files = 0
        countries_data = []

        # 국가별 디렉토리 조회
        try:
            country_dirs = sftp.listdir(base_path)
        except Exception:
            country_dirs = []

        retailer_map = get_retailer_map()

        for country_code in sorted(country_dirs):
            country_path = f"{base_path}/{country_code}"

            # 디렉토리인지 확인
            try:
                stat = sftp.stat(country_path)
                if not (stat.st_mode & 0o40000):
                    continue
            except Exception:
                continue

            # 해당 날짜 폴더 확인
            date_path = f"{country_path}/{date_folder}"
            try:
                sftp.stat(date_path)
            except FileNotFoundError:
                continue

            # 파일 목록 및 용량 조회 (zip 파일만)
            try:
                files = sftp.listdir_attr(date_path)
                zip_files = [f for f in files if f.filename.endswith('.zip') and not (f.st_mode & 0o40000)]

                for f in sorted(zip_files, key=lambda x: x.filename):
                    filename = f.filename
                    parts = filename.replace('.zip', '').split('_')
                    if len(parts) >= 4:
                        file_country = parts[2]
                        file_retailer = '_'.join(parts[3:])
                        retailer_key = f"{file_country}_{file_retailer}"
                        retailer_name = retailer_map.get(retailer_key, file_retailer)
                    else:
                        retailer_name = country_code.upper()

                    file_modified = datetime.fromtimestamp(f.st_mtime).strftime('%Y-%m-%d %H:%M:%S')

                    total_size += f.st_size
                    total_files += 1

                    countries_data.append({
                        'country_code': country_code,
                        'retailer': retailer_name,
                        'path': date_path,
                        'file_count': 1,
                        'size': f.st_size,
                        'files': [{
                            'name': f.filename,
                            'size': f.st_size,
                            'modified': file_modified
                        }]
                    })
            except Exception:
                continue

        sftp.close()
        transport.close()

        # 수집현황과 동일한 순서로 정렬
        targets = get_monitoring_targets()
        def normalize_name(name):
            return name.lower().replace('-', '').replace('_', '')

        retailer_order = {normalize_name(t[1]): idx for idx, t in enumerate(targets)}

        def get_sort_key(item):
            retailer_name = normalize_name(item.get('retailer', ''))
            return retailer_order.get(retailer_name, 999)

        countries_data.sort(key=get_sort_key)

        unique_countries = set(item['country_code'] for item in countries_data)

        data['countries'] = countries_data
        data['summary'] = {
            'total_countries': len(unique_countries),
            'total_files': total_files,
            'total_size': total_size
        }

    except Exception as e:
        data['error'] = log_error(e)
        data['summary'] = {
            'total_countries': 0,
            'total_files': 0,
            'total_size': 0
        }

    return JsonResponse(data)


_SAFE_NAME = re.compile(r'^[a-zA-Z0-9_\-\.]+$')


def _validate_path_segment(value, label):
    """경로 세그먼트 검증 — Path Traversal 방지"""
    if not value or not _SAFE_NAME.match(value):
        return JsonResponse({'error': f'잘못된 {label}입니다.'}, status=400)
    return None


def _connect_fileserver_sftp():
    transport = paramiko.Transport((FILE_SERVER_CONFIG['host'], FILE_SERVER_CONFIG['port']))
    transport.connect(
        username=FILE_SERVER_CONFIG['username'],
        password=FILE_SERVER_CONFIG['password']
    )
    return transport, paramiko.SFTPClient.from_transport(transport)


def fileserver_browse(request):
    """파일서버 탐색 API — 특정 국가의 날짜 폴더 + backup 폴더 리스팅
    - country 없으면 국가 목록만 반환
    - country 있으면 해당 국가의 날짜 폴더 + backup 폴더 파일 리스팅
    """
    date_str = request.GET.get('date')
    country = request.GET.get('country', '').strip()

    base_path = FILE_SERVER_CONFIG['upload_path']

    # country 없으면 국가 목록만 반환 (모니터링 대상 국가만)
    if not country:
        transport, sftp = None, None
        try:
            targets = get_monitoring_targets()
            active_countries = set(t[4] for t in targets if t[4])  # country 컬럼

            transport, sftp = _connect_fileserver_sftp()
            entries = sftp.listdir_attr(base_path)
            countries = []
            for e in sorted(entries, key=lambda x: x.filename):
                if not (e.st_mode & 0o40000):
                    continue
                if e.filename not in active_countries:
                    continue
                countries.append({
                    'name': e.filename,
                    'modified': datetime.fromtimestamp(e.st_mtime).strftime('%Y-%m-%d %H:%M:%S'),
                })
            return JsonResponse({'countries': countries})
        except Exception as e:
            return JsonResponse({'error': log_error(e)}, status=500)
        finally:
            if sftp: sftp.close()
            if transport: transport.close()

    # Path Traversal 방지
    err = _validate_path_segment(country, '국가 코드')
    if err: return err

    # country 있으면 날짜 폴더 + backup 폴더 리스팅
    today = datetime.now().date()
    if date_str:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        if target_date > today:
            target_date = today
    else:
        target_date = (datetime.now() - timedelta(days=1)).date()

    date_folder = target_date.strftime('%Y%m%d')
    country_path = f"{base_path}/{country}"

    def list_files(sftp, dir_path, prefix=None):
        """디렉토리의 파일 목록 반환. prefix 지정 시 해당 접두사로 시작하는 파일만."""
        result = []
        try:
            files = sftp.listdir_attr(dir_path)
        except FileNotFoundError:
            return result
        except Exception:
            return result

        for f in sorted(files, key=lambda x: x.filename):
            if f.st_mode & 0o40000:
                continue
            if prefix and not f.filename.startswith(prefix):
                continue
            result.append({
                'name': f.filename,
                'size': f.st_size,
                'modified': datetime.fromtimestamp(f.st_mtime).strftime('%Y-%m-%d %H:%M:%S'),
            })
        return result

    transport, sftp = None, None
    try:
        transport, sftp = _connect_fileserver_sftp()

        # 국가 디렉토리 존재 확인
        try:
            sftp.stat(country_path)
        except FileNotFoundError:
            return JsonResponse({'error': f'국가 폴더 "{country}"를 찾을 수 없습니다.'}, status=404)

        date_files = list_files(sftp, f"{country_path}/{date_folder}")
        backup_files = list_files(sftp, f"{country_path}/backup", prefix=date_folder)

        return JsonResponse({
            'date': str(target_date),
            'date_folder': date_folder,
            'country': country,
            'date_files': date_files,
            'backup_files': backup_files,
        })

    except Exception as e:
        return JsonResponse({'error': log_error(e)}, status=500)
    finally:
        if sftp: sftp.close()
        if transport: transport.close()


def fileserver_move(request):
    """파일서버 파일 이동 API — 날짜 폴더 → backup 폴더"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST 요청만 허용됩니다.'}, status=405)

    try:
        body = json.loads(request.body)
    except Exception:
        return JsonResponse({'error': '잘못된 요청 형식입니다.'}, status=400)

    country = body.get('country', '').strip()
    date_folder = body.get('date_folder', '').strip()
    files = body.get('files', [])

    if not country or not date_folder or not files:
        return JsonResponse({'error': 'country, date_folder, files가 필요합니다.'}, status=400)

    # Path Traversal 방지
    for label, val in [('국가 코드', country), ('날짜 폴더', date_folder)]:
        err = _validate_path_segment(val, label)
        if err: return err
    for filename in files:
        err = _validate_path_segment(filename, '파일명')
        if err: return err

    base_path = FILE_SERVER_CONFIG['upload_path']
    src_dir = f"{base_path}/{country}/{date_folder}"
    dst_dir = f"{base_path}/{country}/backup"

    transport, sftp = None, None
    try:
        transport, sftp = _connect_fileserver_sftp()

        # backup 폴더 없으면 생성
        try:
            sftp.stat(dst_dir)
        except FileNotFoundError:
            sftp.mkdir(dst_dir)

        moved = []
        failed = []
        skipped = []

        for filename in files:
            src_path = f"{src_dir}/{filename}"
            dst_path = f"{dst_dir}/{filename}"
            try:
                # 대상 파일 존재 여부 확인
                try:
                    sftp.stat(dst_path)
                    skipped.append(filename)
                    continue
                except FileNotFoundError:
                    pass
                sftp.rename(src_path, dst_path)
                moved.append(filename)
            except Exception as e:
                failed.append({'file': filename, 'error': str(e)})

        return JsonResponse({
            'success': len(failed) == 0,
            'moved': moved,
            'failed': failed,
            'skipped': skipped,
        })

    except Exception as e:
        return JsonResponse({'error': log_error(e)}, status=500)
    finally:
        if sftp: sftp.close()
        if transport: transport.close()


def rerun_crawler(request):
    """SSM을 통해 EC2 인스턴스에서 크롤러 재실행 API"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST 요청만 허용됩니다.'}, status=405)

    try:
        body = json.loads(request.body)
    except:
        return JsonResponse({'error': '잘못된 요청 형식입니다.'}, status=400)

    retailer = body.get('retailer')
    crawl_date = body.get('crawl_date')
    created_id = request.user.username if request.user.is_authenticated else None

    if not retailer or not crawl_date:
        return JsonResponse({'error': '리테일러, 날짜가 필요합니다.'}, status=400)

    # DB에서 해당 리테일러의 id, instance_id, instance_region 조회
    try:
        conn = get_ds_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT retailer_id, instance_id, instance_region, schedule_name, region_timezone FROM ssd_crawl_db.ds_monitoring_targets
            WHERE retailer = %s AND is_active = 1
        """, (retailer,))
        row = cursor.fetchone()

        if not row:
            cursor.close()
            conn.close()
            return JsonResponse({'error': '해당 리테일러를 찾을 수 없습니다.'}, status=404)

        retailer_id = row[0]
        instance_id = row[1]
        instance_region = row[2] or SSM_CONFIG['region']
        schedule_name = row[3]
        region_timezone = row[4]

        if not instance_id:
            cursor.close()
            conn.close()
            return JsonResponse({'error': '이 리테일러는 instance_id가 없어 재실행할 수 없습니다.'}, status=400)

        if not schedule_name:
            cursor.close()
            conn.close()
            return JsonResponse({'error': '이 리테일러는 schedule_name이 등록되지 않았습니다.'}, status=400)

    except Exception as e:
        return safe_error(e, 'db')

    # SSM 명령 실행 (Task Scheduler 방식)
    try:
        ssm_client = boto3.client(
            'ssm',
            region_name=instance_region,
            aws_access_key_id=SSM_CONFIG['access_key'],
            aws_secret_access_key=SSM_CONFIG['secret_key']
        )

        commands = [
            f'schtasks /run /tn "{schedule_name}"',
            f'Write-Output "Task {schedule_name} triggered for {retailer} ({crawl_date})"'
        ]

        response = ssm_client.send_command(
            InstanceIds=[instance_id],
            DocumentName='AWS-RunPowerShellScript',
            Parameters={
                'commands': commands
            },
            TimeoutSeconds=60
        )

        command_id = response['Command']['CommandId']

    except Exception as e:
        cursor.close()
        conn.close()
        return safe_error(e)

    now = datetime.now()

    # 재실행 로그 저장 & 배치 자동 생성
    try:
        # 재실행 로그 저장
        cursor.execute("""
            INSERT INTO ssd_crawl_db.ds_monitoring_crawler_rerun_log
            (retailer_id, crawl_date, schedule_name, created_id, instance_id, command_id, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (retailer_id, crawl_date, schedule_name, created_id, instance_id, command_id, now))

        # 배치 로그 자동 생성 (start_time = 리테일러 타임존 기준)
        if region_timezone:
            tz = pytz.timezone(region_timezone)
            local_now = datetime.now(tz)
            batch_start_time = local_now.strftime('%H:%M:%S')
        else:
            batch_start_time = now.strftime('%H:%M:%S')
        batch_memo = f'재실행 ({request.user.username})'
        cursor.execute("""
            INSERT INTO ssd_crawl_db.ds_collection_batch_log
            (date, retailer, start_time, memo)
            VALUES (%s, %s, %s, %s)
        """, (crawl_date, retailer, batch_start_time, batch_memo))

        conn.commit()
    except Exception as e:
        return safe_error(e, 'save')
    finally:
        cursor.close()
        conn.close()

    return JsonResponse({
        'success': True,
        'message': f'{retailer} 크롤러 재실행이 요청되었습니다.',
        'command_id': command_id,
        'instance_id': instance_id,
        'retailer': retailer,
        'crawl_date': crawl_date,
        'schedule_name': schedule_name
    })
