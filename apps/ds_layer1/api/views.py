"""
DS Layer 1 API: 기본 통계 검수
인스턴스별/지역별 수집 현황 API
"""

from django.http import JsonResponse
from datetime import datetime, timedelta, date
from apps.common.db import get_ds_connection
import pytz

# 모니터링 대상 테이블 (table_name, retailer, region, korea_time, country, mall_name)
MONITORING_TARGETS = [
    ('amazon_price_crawl_tbl_usa_v2', 'Amazon_USA', '미국(오하이오)', '22:00', 'usa', 'amazon'),
    ('bestbuy_price_crawl_tbl_usa_v2', 'BestBuy_USA', '미국(오하이오)', '23:00', 'usa', 'bestbuy'),
    ('amazon_price_crawl_tbl_jp_v2', 'Amazon_JP', '아시아(도쿄)', '09:00', 'jp', 'amazon'),
    ('amazon_price_crawl_tbl_ind_v2', 'Amazon_IN', '아시아(뭄바이)', '12:30', 'in', 'amazon'),
    ('danawa_price_crawl_tbl_kr_v2', 'Danawa_KR', '아시아(서울)', '09:00', 'kr', 'danawa'),
    ('amazon_price_crawl_tbl_uk_v2', 'Amazon_GB', '유럽(런던)', '17:00', 'gb', 'amazon'),
    ('currys_price_crawl_tbl_gb_v2', 'Currys_GB', '유럽(런던)', '17:00', 'gb', 'currys'),
    ('amazon_price_crawl_tbl_it_v2', 'Amazon_IT', '유럽(밀라노)', '16:00', 'it', 'amazon'),
    ('amazon_price_crawl_tbl_es_v2', 'Amazon_ES', '유럽(스페인)', '16:00', 'es', 'amazon'),
    ('amazon_price_crawl_tbl_fr_v2', 'Amazon_FR', '유럽(파리)', '16:00', 'fr', 'amazon'),
    ('fnac_price_crawl_tbl_fr', 'Fnac_FR', '유럽(파리)', '17:00', 'fr', 'fnac'),
    ('amazon_price_crawl_tbl_nl', 'Amazon_NL', '유럽(파리)', '16:00', 'nl', 'amazon'),
    ('coolblue_price_crawl_tbl_nl_v2', 'Coolblue_NL', '유럽(파리)', '16:00', 'nl', 'coolblue'),
    ('amazon_price_crawl_tbl_de_v2', 'Amazon_DE', '유럽(프랑크푸르트)', '16:00', 'de', 'amazon'),
    ('mediamarkt_price_crawl_tbl_de_v2', 'MediaMarkt_DE', '유럽(프랑크푸르트)', '17:00', 'de', 'mediamarkt'),
    ('xkom_price_crawl_tbl_pl_v2', 'X-Kom_PL', '유럽(프랑크푸르트)', '17:00', 'pl', 'x-kom'),
    ('centrecom_price_crawl_tbl_au', 'CentreCom_AU', '호주', '07:00', 'au', 'centrecom'),
]


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

        # 한국 다나와는 2배로 계산
        if country == 'kr' and mall_name == 'danawa':
            count = count * 2

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
        crawl_time_plus_1h = crawl_time + timedelta(hours=1)

        if now_kst < crawl_time:
            return 'pending'  # 대기중
        elif now_kst < crawl_time_plus_1h:
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

        for idx, (table_name, retailer, region, korea_time, country, mall_name) in enumerate(MONITORING_TARGETS, 1):
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
            'total_tables': len(MONITORING_TARGETS),
            'total_expected': total_expected,
            'total_actual': total_actual,
            'total_completion_rate': total_completion_rate,
            'status': 'success' if total_completion_rate >= 95 else ('warning' if total_completion_rate >= 80 else 'danger')
        }

    except Exception as e:
        data['error'] = str(e)
        data['summary'] = {
            'total_tables': len(MONITORING_TARGETS),
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
        for table_name, retailer, region, korea_time, country, mall_name in MONITORING_TARGETS:
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
    valid_tables = [t[0] for t in MONITORING_TARGETS]
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
        retailer_info = next((t for t in MONITORING_TARGETS if t[0] == table_name), None)

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
        valid_tables = [t[0] for t in MONITORING_TARGETS]
        if table_name not in valid_tables:
            return JsonResponse({'error': '유효하지 않은 테이블명입니다.'})
        targets = [t for t in MONITORING_TARGETS if t[0] == table_name]
    else:
        targets = MONITORING_TARGETS

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
