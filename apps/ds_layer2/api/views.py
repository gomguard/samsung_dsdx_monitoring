"""
DS Layer 2 API: 데이터 품질 검수 (NULL 필드 체크)
날짜별 NULL 필드 현황 조회 API

검증 조건:
1. title이 NULL이거나 imageurl이 'https://'로 시작하지 않으면 → 기본 필드 NULL
2. title과 imageurl이 둘 다 유효할 때:
   - retailprice, ships_from, sold_by 3개 모두 NULL → 정상
   - retailprice, ships_from, sold_by 일부만 NULL → 비정상 (부분 NULL)
"""

from django.http import JsonResponse
from datetime import datetime, timedelta
from apps.common.db import get_ds_connection

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

# 체크할 NULL 필드 목록
NULL_CHECK_FIELDS = ['title', 'imageurl', 'retailprice', 'ships_from', 'sold_by']


def get_quality_counts(cursor, table_name, target_date):
    """
    특정 테이블의 데이터 품질 현황 조회

    검증 조건:
    - title NULL: title이 NULL이거나 빈 문자열
    - imageurl NULL: title 유효, imageurl이 NULL이거나 빈 문자열
    - imageurl 무효: title 유효, imageurl이 있지만 'https://'로 시작하지 않음
    - 부분 NULL: title/imageurl 유효하지만 retailprice,ships_from,sold_by 중 일부만 NULL (비정상)
    - 전체 NULL: title/imageurl 유효하고 retailprice,ships_from,sold_by 모두 NULL (정상)
    """
    date_str = target_date.strftime('%Y%m%d')
    start_datetime = f"{date_str}0000"
    next_date = (target_date + timedelta(days=1)).strftime('%Y%m%d')
    end_datetime = f"{next_date}0000"

    results = {
        'total': 0,
        'title_null': 0,
        'imageurl_null': 0,  # imageurl이 NULL
        'imageurl_invalid': 0,  # imageurl이 있지만 형식 오류
        'partial_null': 0,  # 일부만 NULL (비정상)
        'all_null': 0,  # 3개 모두 NULL (정상)
        'valid': 0,  # 완전히 정상
    }

    try:
        base_query = f"""
            SELECT DISTINCT * FROM samsung_ds_retail_com.{table_name}
            WHERE crawl_strdatetime >= %s AND crawl_strdatetime < %s
        """

        # 1. 전체 건수
        cursor.execute(f"SELECT COUNT(*) FROM ({base_query}) A", (start_datetime, end_datetime))
        results['total'] = cursor.fetchone()[0] or 0

        # 2. title NULL 건수
        cursor.execute(f"""
            SELECT COUNT(*) FROM ({base_query}) A
            WHERE title IS NULL OR TRIM(title) = ''
        """, (start_datetime, end_datetime))
        results['title_null'] = cursor.fetchone()[0] or 0

        # 3. imageurl NULL 건수 (title은 유효한데 imageurl이 NULL인 경우)
        cursor.execute(f"""
            SELECT COUNT(*) FROM ({base_query}) A
            WHERE (title IS NOT NULL AND TRIM(title) != '')
            AND (imageurl IS NULL OR TRIM(imageurl) = '')
        """, (start_datetime, end_datetime))
        results['imageurl_null'] = cursor.fetchone()[0] or 0

        # 4. imageurl 무효 건수 (title 유효, imageurl이 있지만 https://로 시작하지 않음)
        cursor.execute(f"""
            SELECT COUNT(*) FROM ({base_query}) A
            WHERE (title IS NOT NULL AND TRIM(title) != '')
            AND (imageurl IS NOT NULL AND TRIM(imageurl) != '')
            AND imageurl NOT LIKE 'https://%%'
        """, (start_datetime, end_datetime))
        results['imageurl_invalid'] = cursor.fetchone()[0] or 0

        # 5. title과 imageurl이 둘 다 유효한 데이터 중에서 검사
        # (title 유효 AND imageurl이 https://로 시작)
        valid_base = f"""
            SELECT * FROM ({base_query}) A
            WHERE (title IS NOT NULL AND TRIM(title) != '')
            AND (imageurl IS NOT NULL AND imageurl LIKE 'https://%%')
        """

        # 4-1. 3개 필드 모두 NULL (정상)
        cursor.execute(f"""
            SELECT COUNT(*) FROM ({valid_base}) B
            WHERE (retailprice IS NULL OR TRIM(retailprice) = '')
            AND (ships_from IS NULL OR TRIM(ships_from) = '')
            AND (sold_by IS NULL OR TRIM(sold_by) = '')
        """, (start_datetime, end_datetime))
        results['all_null'] = cursor.fetchone()[0] or 0

        # 4-2. 3개 필드 중 일부만 NULL (비정상)
        # 1개 또는 2개만 NULL인 경우
        cursor.execute(f"""
            SELECT COUNT(*) FROM ({valid_base}) B
            WHERE NOT (
                -- 3개 모두 유효
                ((retailprice IS NOT NULL AND TRIM(retailprice) != '')
                 AND (ships_from IS NOT NULL AND TRIM(ships_from) != '')
                 AND (sold_by IS NOT NULL AND TRIM(sold_by) != ''))
                OR
                -- 3개 모두 NULL
                ((retailprice IS NULL OR TRIM(retailprice) = '')
                 AND (ships_from IS NULL OR TRIM(ships_from) = '')
                 AND (sold_by IS NULL OR TRIM(sold_by) = ''))
            )
        """, (start_datetime, end_datetime))
        results['partial_null'] = cursor.fetchone()[0] or 0

        # 4-3. 완전히 정상 (title, imageurl 유효 + 3개 필드 모두 유효)
        cursor.execute(f"""
            SELECT COUNT(*) FROM ({valid_base}) B
            WHERE (retailprice IS NOT NULL AND TRIM(retailprice) != '')
            AND (ships_from IS NOT NULL AND TRIM(ships_from) != '')
            AND (sold_by IS NOT NULL AND TRIM(sold_by) != '')
        """, (start_datetime, end_datetime))
        results['valid'] = cursor.fetchone()[0] or 0

    except Exception as e:
        results['error'] = str(e)

    return results


def layer_stats(request):
    """DS Layer 2 전체 데이터 품질 통계 API"""
    date_str = request.GET.get('date')

    if date_str:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    else:
        target_date = (datetime.now() - timedelta(days=1)).date()

    data = {
        'timestamp': datetime.now().isoformat(),
        'date': str(target_date),
        'layer': 2,
        'data_source': 'ds',
        'results': [],
        'summary': {}
    }

    try:
        conn = get_ds_connection()
        cursor = conn.cursor()

        results = []
        total_records = 0
        total_title_null = 0
        total_imageurl_null = 0
        total_imageurl_invalid = 0
        total_partial_null = 0
        total_all_null = 0
        total_valid = 0

        for idx, (table_name, retailer, region, korea_time, country, mall_name) in enumerate(MONITORING_TARGETS, 1):
            quality = get_quality_counts(cursor, table_name, target_date)

            total = quality.get('total', 0)
            total_records += total

            title_null = quality.get('title_null', 0)
            imageurl_null = quality.get('imageurl_null', 0)
            imageurl_invalid = quality.get('imageurl_invalid', 0)
            partial_null = quality.get('partial_null', 0)
            all_null = quality.get('all_null', 0)
            valid = quality.get('valid', 0)

            total_title_null += title_null
            total_imageurl_null += imageurl_null
            total_imageurl_invalid += imageurl_invalid
            total_partial_null += partial_null
            total_all_null += all_null
            total_valid += valid

            # 비정상 건수 = title NULL + imageurl NULL + imageurl 무효 + 부분 NULL
            error_count = title_null + imageurl_null + imageurl_invalid + partial_null

            # 상태 판정
            if total == 0:
                status = 'pending'
            elif error_count == 0:
                status = 'success'
            elif error_count < total * 0.05:  # 5% 미만
                status = 'warning'
            else:
                status = 'danger'

            results.append({
                'no': idx,
                'table_name': table_name,
                'retailer': retailer,
                'region': region,
                'country': country.upper(),
                'total': total,
                'title_null': title_null,
                'imageurl_null': imageurl_null,
                'imageurl_invalid': imageurl_invalid,
                'partial_null': partial_null,
                'all_null': all_null,
                'valid': valid,
                'error_count': error_count,
                'status': status
            })

        cursor.close()
        conn.close()

        # 전체 비정상 건수
        total_error = total_title_null + total_imageurl_null + total_imageurl_invalid + total_partial_null

        # 전체 상태
        if total_records == 0:
            overall_status = 'pending'
        elif total_error == 0:
            overall_status = 'success'
        elif total_error < total_records * 0.05:
            overall_status = 'warning'
        else:
            overall_status = 'danger'

        data['results'] = results
        data['summary'] = {
            'total_tables': len(MONITORING_TARGETS),
            'total_records': total_records,
            'title_null': total_title_null,
            'imageurl_null': total_imageurl_null,
            'imageurl_invalid': total_imageurl_invalid,
            'partial_null': total_partial_null,
            'all_null': total_all_null,
            'valid': total_valid,
            'total_error': total_error,
            'status': overall_status
        }

    except Exception as e:
        data['error'] = str(e)
        data['summary'] = {
            'total_tables': len(MONITORING_TARGETS),
            'total_records': 0,
            'total_error': 0,
            'status': 'error'
        }

    return JsonResponse(data)


def table_null_detail(request):
    """
    특정 테이블의 비정상 데이터 상세 조회 API

    error_type:
    - title_null: title이 NULL인 데이터
    - imageurl_null: title 유효, imageurl이 NULL
    - imageurl_invalid: title 유효, imageurl이 있지만 형식 오류
    - partial_null: title/imageurl 유효, retailprice/ships_from/sold_by 일부만 NULL
    """
    date_str = request.GET.get('date')
    table_name = request.GET.get('table')
    error_type = request.GET.get('error_type', 'title_null')
    page = int(request.GET.get('page', 1))
    page_size = int(request.GET.get('page_size', 50))

    if not table_name:
        return JsonResponse({'error': '테이블명을 입력하세요.'})

    valid_tables = [t[0] for t in MONITORING_TARGETS]
    if table_name not in valid_tables:
        return JsonResponse({'error': '유효하지 않은 테이블명입니다.'})

    valid_error_types = ['title_null', 'imageurl_null', 'imageurl_invalid', 'partial_null']
    if error_type not in valid_error_types:
        return JsonResponse({'error': f'유효하지 않은 에러 타입입니다.'})

    if date_str:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    else:
        target_date = (datetime.now() - timedelta(days=1)).date()

    data = {
        'timestamp': datetime.now().isoformat(),
        'date': str(target_date),
        'table': table_name,
        'error_type': error_type,
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

        base_query = f"""
            SELECT DISTINCT * FROM samsung_ds_retail_com.{table_name}
            WHERE crawl_strdatetime >= %s AND crawl_strdatetime < %s
        """

        # 에러 타입별 WHERE 조건
        if error_type == 'title_null':
            where_condition = "WHERE title IS NULL OR TRIM(title) = ''"
        elif error_type == 'imageurl_null':
            where_condition = """
                WHERE (title IS NOT NULL AND TRIM(title) != '')
                AND (imageurl IS NULL OR TRIM(imageurl) = '')
            """
        elif error_type == 'imageurl_invalid':
            where_condition = """
                WHERE (title IS NOT NULL AND TRIM(title) != '')
                AND (imageurl IS NOT NULL AND TRIM(imageurl) != '')
                AND imageurl NOT LIKE 'https://%%'
            """
        else:  # partial_null
            where_condition = """
                WHERE (title IS NOT NULL AND TRIM(title) != '')
                AND (imageurl IS NOT NULL AND imageurl LIKE 'https://%%')
                AND NOT (
                    ((retailprice IS NOT NULL AND TRIM(retailprice) != '')
                     AND (ships_from IS NOT NULL AND TRIM(ships_from) != '')
                     AND (sold_by IS NOT NULL AND TRIM(sold_by) != ''))
                    OR
                    ((retailprice IS NULL OR TRIM(retailprice) = '')
                     AND (ships_from IS NULL OR TRIM(ships_from) = '')
                     AND (sold_by IS NULL OR TRIM(sold_by) = ''))
                )
            """

        # 건수 조회
        count_query = f"SELECT COUNT(*) FROM ({base_query}) A {where_condition}"
        cursor.execute(count_query, (start_datetime, end_datetime))
        total_count = cursor.fetchone()[0]

        # 페이징된 데이터 조회
        offset = (page - 1) * page_size
        query = f"""
            SELECT title, retailprice, ships_from, sold_by, imageurl, producturl
            FROM ({base_query}) A
            {where_condition}
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

        retailer_info = next((t for t in MONITORING_TARGETS if t[0] == table_name), None)

        data['retailer'] = retailer_info[1] if retailer_info else table_name
        data['region'] = retailer_info[2] if retailer_info else ''
        data['country'] = retailer_info[4].upper() if retailer_info else ''
        data['total_count'] = total_count
        data['total_pages'] = (total_count + page_size - 1) // page_size if total_count > 0 else 1
        data['data'] = items

    except Exception as e:
        data['error'] = str(e)

    return JsonResponse(data)
