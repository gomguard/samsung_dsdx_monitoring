"""
DS Layer 1 API: 기본 통계 검수
인스턴스별/지역별 수집 현황 API
"""

from django.http import JsonResponse
from datetime import datetime, timedelta
from apps.common.db import get_ds_connection

# 모니터링 대상 테이블 (monitoring_project/ds/monitoring_targets.py 기반)
MONITORING_TARGETS = [
    ('amazon_price_crawl_tbl_usa_v2', 'Amazon', '미국(오하이오)', '22:00', 'usa', 'amazon'),
    ('bestbuy_price_crawl_tbl_usa_v2', 'Best Buy', '미국(오하이오)', '23:00', 'usa', 'bestbuy'),
    ('amazon_price_crawl_tbl_jp_v2', 'Amazon', '아시아(도쿄)', '09:00', 'jp', 'amazon'),
    ('amazon_price_crawl_tbl_ind_v2', 'Amazon', '아시아(뭄바이)', '12:30', 'in', 'amazon'),
    ('danawa_price_crawl_tbl_kr_v2', 'Danawa', '아시아(서울)', '09:00', 'kr', 'danawa'),
    ('amazon_price_crawl_tbl_uk_v2', 'Amazon', '유럽(런던)', '17:00', 'gb', 'amazon'),
    ('currys_price_crawl_tbl_gb_v2', 'Currys', '유럽(런던)', '17:00', 'gb', 'currys'),
    ('amazon_price_crawl_tbl_it_v2', 'Amazon', '유럽(밀라노)', '16:00', 'it', 'amazon'),
    ('amazon_price_crawl_tbl_es_v2', 'Amazon', '유럽(스페인)', '16:00', 'es', 'amazon'),
    ('amazon_price_crawl_tbl_fr_v2', 'Amazon FR', '유럽(파리)', '16:00', 'fr', 'amazon'),
    ('fnac_price_crawl_tbl_fr', 'Fnac', '유럽(파리)', '17:00', 'fr', 'fnac'),
    ('amazon_price_crawl_tbl_nl', 'Amazon NL', '유럽(파리)', '16:00', 'nl', 'amazon'),
    ('coolblue_price_crawl_tbl_nl_v2', 'Coolblue', '유럽(파리)', '16:00', 'nl', 'coolblue'),
    ('amazon_price_crawl_tbl_de_v2', 'Amazon', '유럽(프랑크푸르트)', '16:00', 'de', 'amazon'),
    ('mediamarkt_price_crawl_tbl_de_v2', 'MediaMarkt', '유럽(프랑크푸르트)', '17:00', 'de', 'mediamarkt'),
    ('xkom_price_crawl_tbl_pl_v2', 'X-Kom', '유럽(프랑크푸르트)', '17:00', 'pl', 'x-kom'),
    ('centrecom_price_crawl_tbl_au', 'Centre Com', '호주', '07:00', 'au', 'centrecom'),
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

            # 상태 판단
            if completion_rate >= 95:
                status = 'success'
            elif completion_rate >= 80:
                status = 'warning'
            elif completion_rate >= 0:
                status = 'danger'
            else:
                status = 'error'

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

            # 상태 판단
            if completion_rate >= 95:
                status = 'success'
            elif completion_rate >= 80:
                status = 'warning'
            elif completion_rate >= 0:
                status = 'danger'
            else:
                status = 'error'

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
