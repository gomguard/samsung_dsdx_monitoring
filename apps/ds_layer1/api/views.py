"""
DS Layer 1 API: 기본 통계 검수
인스턴스별/지역별 수집 현황 API
파일서버 용량 조회 API
"""

from django.http import JsonResponse
from datetime import datetime, timedelta, date
from apps.common.db import get_ds_connection
from config.config import FILE_SERVER_CONFIG
from apps.common.targets import load_monitoring_targets, get_retailer_map
import pytz
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
    kst = pytz.timezone('Asia/Seoul')
    now_kst = datetime.now(kst)
    today = now_kst.date()

    # 조회 날짜가 오늘이 아니면 완료율 기반 판단
    if target_date != today:
        if completion_rate >= 95:
            return 'success'
        elif completion_rate >= 80:
            return 'warning'
        elif completion_rate >= 0:
            return 'danger'
        else:
            return 'error'

    # 오늘 날짜인 경우 시간 비교
    try:
        hour, minute = map(int, korea_time_str.split(':'))
        crawl_time = now_kst.replace(hour=hour, minute=minute, second=0, microsecond=0)
        crawl_time_plus_2h = crawl_time + timedelta(hours=2)

        if now_kst < crawl_time:
            return 'pending'  # 대기중
        elif now_kst < crawl_time_plus_2h:
            # 수집중이지만 100% 달성했으면 결과 표시
            if completion_rate >= 100:
                return 'success'
            return 'collecting'  # 수집중
        else:
            # 수집 완료 시간 지남 - 완료율 기반 판단
            if completion_rate >= 95:
                return 'success'
            elif completion_rate >= 80:
                return 'warning'
            elif completion_rate >= 0:
                return 'danger'
            else:
                return 'error'
    except:
        # 시간 파싱 실패 시 완료율 기반 판단
        if completion_rate >= 95:
            return 'success'
        elif completion_rate >= 80:
            return 'warning'
        elif completion_rate >= 0:
            return 'danger'
        else:
            return 'error'


def layer_stats(request):
    """DS Layer 1 전체 통계 API"""
    date_str = request.GET.get('date')

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

        total_expected = 0
        total_actual = 0
        results = []

        for idx, (table_name, retailer, region, korea_time, country, mall_name) in enumerate(get_monitoring_targets(), 1):
            expected = get_expected_count(cursor, country, mall_name)
            actual = get_crawl_count(cursor, table_name, target_date)

            # 완료율 계산
            if expected > 0 and actual >= 0:
                completion_rate = round((actual / expected) * 100, 1)
            elif expected == 0:
                completion_rate = 0
            else:
                completion_rate = -1

            if expected >= 0:
                total_expected += expected
            if actual >= 0:
                total_actual += actual

            # 상태 판단 (시간 기반)
            status = get_collection_status(korea_time, target_date, completion_rate)

            results.append({
                'no': idx,
                'table_name': table_name,
                'retailer': retailer,
                'region': region,
                'korea_time': korea_time,
                'country': country.upper(),
                'expected': expected,
                'actual': actual,
                'completion_rate': completion_rate,
                'status': status
            })

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
            'status': 'success' if total_completion_rate >= 95 else ('warning' if total_completion_rate >= 80 else 'danger')
        }

    except Exception as e:
        data['error'] = str(e)
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
            if region_data['completion_rate'] >= 95:
                region_data['status'] = 'success'
            elif region_data['completion_rate'] >= 80:
                region_data['status'] = 'warning'
            else:
                region_data['status'] = 'danger'

        cursor.close()
        conn.close()

        data['regions'] = regions

    except Exception as e:
        data['error'] = str(e)

    return JsonResponse(data)


def table_detail(request):
    """특정 테이블의 수집 데이터 상세 조회 API"""
    date_str = request.GET.get('date')
    table_name = request.GET.get('table')
    page = int(request.GET.get('page', 1))
    page_size = int(request.GET.get('page_size', 50))

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
        'data': []
    }

    try:
        conn = get_ds_connection()
        cursor = conn.cursor()

        date_str_fmt = target_date.strftime('%Y%m%d')
        start_datetime = f"{date_str_fmt}0000"
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
        query = f"""
            SELECT title, retailprice, ships_from, sold_by, imageurl, producturl
            FROM (
                SELECT DISTINCT * FROM samsung_ds_retail_com.{table_name}
                WHERE crawl_strdatetime >= %s AND crawl_strdatetime < %s
            ) A
            ORDER BY title
            LIMIT %s OFFSET %s
        """

        cursor.execute(query, (start_datetime, end_datetime, page_size, offset))
        rows = cursor.fetchall()

        items = []
        for row in rows:
            items.append({
                'title': row[0] or '',
                'retailprice': row[1] or '',
                'ships_from': row[2] or '',
                'sold_by': row[3] or '',
                'imageurl': row[4] or '',
                'producturl': row[5] or ''
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
        data['error'] = str(e)

    return JsonResponse(data)


def date_range_stats(request):
    """날짜 범위 통계 조회 API"""
    start_date_str = request.GET.get('start_date')
    end_date_str = request.GET.get('end_date')
    table_name = request.GET.get('table')  # 선택적: 특정 테이블만 조회

    if not start_date_str or not end_date_str:
        return JsonResponse({'error': '시작일과 종료일을 입력하세요.'})

    try:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
    except ValueError:
        return JsonResponse({'error': '날짜 형식이 올바르지 않습니다. (YYYY-MM-DD)'})

    # 최대 30일로 제한
    if (end_date - start_date).days > 30:
        return JsonResponse({'error': '최대 30일까지 조회 가능합니다.'})

    if end_date < start_date:
        return JsonResponse({'error': '종료일이 시작일보다 빠릅니다.'})

    # 특정 테이블 필터
    if table_name:
        valid_tables = [t[0] for t in get_monitoring_targets()]
        if table_name not in valid_tables:
            return JsonResponse({'error': '유효하지 않은 테이블명입니다.'})
        targets = [t for t in get_monitoring_targets() if t[0] == table_name]
    else:
        targets = get_monitoring_targets()

    data = {
        'timestamp': datetime.now().isoformat(),
        'start_date': str(start_date),
        'end_date': str(end_date),
        'dates': [],
        'retailers': []
    }

    try:
        conn = get_ds_connection()
        cursor = conn.cursor()

        # 날짜 목록 생성
        date_list = []
        current_date = start_date
        while current_date <= end_date:
            date_list.append(current_date)
            current_date += timedelta(days=1)

        data['dates'] = [str(d) for d in date_list]

        # 리테일러별 날짜별 데이터 수집
        retailers_data = []
        for table_name, retailer, region, korea_time, country, mall_name in targets:
            expected = get_expected_count(cursor, country, mall_name)

            daily_stats = []
            for target_date in date_list:
                actual = get_crawl_count(cursor, table_name, target_date)

                if expected > 0 and actual >= 0:
                    completion_rate = round((actual / expected) * 100, 1)
                elif expected == 0:
                    completion_rate = 0
                else:
                    completion_rate = -1

                if completion_rate >= 95:
                    status = 'success'
                elif completion_rate >= 80:
                    status = 'warning'
                elif completion_rate >= 0:
                    status = 'danger'
                else:
                    status = 'error'

                daily_stats.append({
                    'date': str(target_date),
                    'actual': actual,
                    'completion_rate': completion_rate,
                    'status': status
                })

            retailers_data.append({
                'table_name': table_name,
                'retailer': retailer,
                'region': region,
                'country': country.upper(),
                'expected': expected,
                'daily_stats': daily_stats
            })

        cursor.close()
        conn.close()

        data['retailers'] = retailers_data

    except Exception as e:
        data['error'] = str(e)

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


def fileserver_stats(request):
    """파일서버 날짜별 용량 조회 API"""
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
                # 해당 날짜 폴더가 없으면 스킵
                continue

            # 파일 목록 및 용량 조회 (zip 파일만)
            try:
                files = sftp.listdir_attr(date_path)

                # zip 파일만 필터링
                zip_files = [f for f in files if f.filename.endswith('.zip') and not (f.st_mode & 0o40000)]

                # 리테일러 이름 찾기 (CSV 기반)
                retailer_map = get_retailer_map()

                # zip 파일 상세 정보 (리테일러별로 분리)
                for f in sorted(zip_files, key=lambda x: x.filename):
                    # 파일명에서 리테일러 추출: 20260102_172616_de_mediamarkt.zip -> mediamarkt
                    filename = f.filename
                    parts = filename.replace('.zip', '').split('_')
                    # parts: ['20260102', '172616', 'de', 'mediamarkt']
                    if len(parts) >= 4:
                        file_country = parts[2]
                        file_retailer = '_'.join(parts[3:])  # 리테일러 이름에 _가 있을 수 있음
                        retailer_key = f"{file_country}_{file_retailer}"
                        retailer_name = retailer_map.get(retailer_key, file_retailer)
                    else:
                        retailer_name = country_code.upper()

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
                            'modified': datetime.fromtimestamp(f.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
                        }]
                    })
            except Exception as e:
                continue

        sftp.close()
        transport.close()

        # 고유 국가 수 계산
        unique_countries = set(item['country_code'] for item in countries_data)

        # 수집현황과 동일한 순서로 정렬 (monitoring_targets.csv 순서 기준)
        targets = get_monitoring_targets()
        # retailer 이름으로 순서 매핑 (대소문자, 하이픈 무시)
        def normalize_name(name):
            return name.lower().replace('-', '').replace('_', '')

        retailer_order = {normalize_name(t[1]): idx for idx, t in enumerate(targets)}

        def get_sort_key(item):
            retailer_name = normalize_name(item.get('retailer', ''))
            return retailer_order.get(retailer_name, 999)

        countries_data.sort(key=get_sort_key)

        data['countries'] = countries_data
        data['summary'] = {
            'total_countries': len(unique_countries),
            'total_files': total_files,
            'total_size': total_size
        }

    except Exception as e:
        data['error'] = str(e)
        data['summary'] = {
            'total_countries': 0,
            'total_files': 0,
            'total_size': 0
        }

    return JsonResponse(data)
