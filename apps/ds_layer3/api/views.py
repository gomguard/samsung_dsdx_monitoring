"""
DS Layer 3 API: 이상치/반복 에러 검수
매일 반복적으로 발생하는 에러 추적

검증 조건:
- producturl을 기준으로 동일 상품 식별
- 연속된 날짜에 동일한 에러가 발생하는 상품 추적
- 에러 유형: title_null, imageurl_null, imageurl_invalid, partial_null
- 신규(1일) vs 반복(2일+) 구분
"""

from django.http import JsonResponse
from datetime import datetime, timedelta
from apps.common.db import get_ds_connection
from apps.common.targets import load_monitoring_targets


def get_monitoring_targets():
    """CSV에서 모니터링 대상 목록 로드"""
    return load_monitoring_targets()


def get_error_products_for_date(cursor, table_name, target_date, error_type):
    """특정 날짜의 에러 상품 producturl 목록 조회"""
    date_str = target_date.strftime('%Y%m%d')
    start_datetime = f"{date_str}0000"
    next_date = (target_date + timedelta(days=1)).strftime('%Y%m%d')
    end_datetime = f"{next_date}0000"

    base_query = f"""
        SELECT DISTINCT * FROM samsung_ds_retail_com.{table_name}
        WHERE crawl_strdatetime >= %s AND crawl_strdatetime < %s
    """

    # 에러 타입별 WHERE 조건
    if error_type == 'title_null':
        where_condition = "WHERE (title IS NULL OR TRIM(title) = '')"
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

    query = f"""
        SELECT producturl FROM ({base_query}) A
        {where_condition}
        AND producturl IS NOT NULL AND TRIM(producturl) != ''
    """

    cursor.execute(query, (start_datetime, end_datetime))
    return set(row[0] for row in cursor.fetchall())


def get_error_analysis(cursor, table_name, target_date, days=3):
    """
    에러 상품 분석 - 신규(1일)와 반복(2일+) 구분
    returns: {error_type: {producturl: days_count}}
    """
    error_types = ['title_null', 'imageurl_null', 'imageurl_invalid', 'partial_null']
    result = {et: {} for et in error_types}

    for error_type in error_types:
        # 각 날짜별 에러 상품 수집 (오늘부터 days일 전까지)
        daily_errors = []
        for i in range(days):
            check_date = target_date - timedelta(days=i)
            try:
                products = get_error_products_for_date(cursor, table_name, check_date, error_type)
                daily_errors.append(products)
            except:
                daily_errors.append(set())

        # 오늘(조회일) 에러가 있는 상품들에 대해 연속일 계산
        today_errors = daily_errors[0] if daily_errors else set()

        for product in today_errors:
            # 연속일 계산 (오늘부터 과거로)
            consecutive_days = 1
            for i in range(1, len(daily_errors)):
                if product in daily_errors[i]:
                    consecutive_days += 1
                else:
                    break
            result[error_type][product] = consecutive_days

    return result


def layer_stats(request):
    """DS Layer 3 전체 에러 통계 API - 신규/반복 구분"""
    date_str = request.GET.get('date')
    days = int(request.GET.get('days', 3))  # 분석할 기간

    if days < 1:
        days = 1
    elif days > 7:
        days = 7

    if date_str:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    else:
        target_date = (datetime.now() - timedelta(days=1)).date()

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
        conn = get_ds_connection()
        cursor = conn.cursor()

        results = []
        # 신규(1일)와 반복(2일+) 각각 집계
        total_new = {'title_null': 0, 'imageurl_null': 0, 'imageurl_invalid': 0, 'partial_null': 0, 'total': 0}
        total_recurring = {'title_null': 0, 'imageurl_null': 0, 'imageurl_invalid': 0, 'partial_null': 0, 'total': 0}

        for idx, (table_name, retailer, region, korea_time, country, mall_name) in enumerate(get_monitoring_targets(), 1):
            try:
                analysis = get_error_analysis(cursor, table_name, target_date, days)

                # 각 에러 타입별 신규/반복 카운트
                new_counts = {}
                recurring_counts = {}

                for error_type in ['title_null', 'imageurl_null', 'imageurl_invalid', 'partial_null']:
                    products = analysis.get(error_type, {})
                    new_count = sum(1 for p, d in products.items() if d == 1)
                    recurring_count = sum(1 for p, d in products.items() if d >= 2)
                    new_counts[error_type] = new_count
                    recurring_counts[error_type] = recurring_count

                    total_new[error_type] += new_count
                    total_recurring[error_type] += recurring_count

                new_total = sum(new_counts.values())
                recurring_total = sum(recurring_counts.values())
                total_new['total'] += new_total
                total_recurring['total'] += recurring_total

                # 상태 판정: 정상 또는 이상만 (경고 없음)
                if recurring_total == 0 and new_total == 0:
                    status = 'success'
                else:
                    status = 'danger'

                results.append({
                    'no': idx,
                    'table_name': table_name,
                    'retailer': retailer,
                    'region': region,
                    'country': country.upper(),
                    # 신규(1일)
                    'new_title_null': new_counts['title_null'],
                    'new_imageurl_null': new_counts['imageurl_null'],
                    'new_imageurl_invalid': new_counts['imageurl_invalid'],
                    'new_partial_null': new_counts['partial_null'],
                    'new_total': new_total,
                    # 반복(2일+)
                    'recurring_title_null': recurring_counts['title_null'],
                    'recurring_imageurl_null': recurring_counts['imageurl_null'],
                    'recurring_imageurl_invalid': recurring_counts['imageurl_invalid'],
                    'recurring_partial_null': recurring_counts['partial_null'],
                    'recurring_total': recurring_total,
                    # 전체
                    'total': new_total + recurring_total,
                    'status': status
                })
            except Exception as e:
                results.append({
                    'no': idx,
                    'table_name': table_name,
                    'retailer': retailer,
                    'region': region,
                    'country': country.upper(),
                    'new_title_null': 0, 'new_imageurl_null': 0, 'new_imageurl_invalid': 0, 'new_partial_null': 0, 'new_total': 0,
                    'recurring_title_null': 0, 'recurring_imageurl_null': 0, 'recurring_imageurl_invalid': 0, 'recurring_partial_null': 0, 'recurring_total': 0,
                    'total': 0,
                    'status': 'error',
                    'error': str(e)
                })

        cursor.close()
        conn.close()

        # 전체 상태: 정상 또는 이상만 (경고 없음)
        if total_recurring['total'] == 0 and total_new['total'] == 0:
            overall_status = 'success'
        else:
            overall_status = 'danger'

        data['results'] = results
        data['summary'] = {
            'total_tables': len(get_monitoring_targets()),
            # 신규(1일)
            'new_title_null': total_new['title_null'],
            'new_imageurl_null': total_new['imageurl_null'],
            'new_imageurl_invalid': total_new['imageurl_invalid'],
            'new_partial_null': total_new['partial_null'],
            'new_total': total_new['total'],
            # 반복(2일+)
            'recurring_title_null': total_recurring['title_null'],
            'recurring_imageurl_null': total_recurring['imageurl_null'],
            'recurring_imageurl_invalid': total_recurring['imageurl_invalid'],
            'recurring_partial_null': total_recurring['partial_null'],
            'recurring_total': total_recurring['total'],
            # 전체
            'total': total_new['total'] + total_recurring['total'],
            'status': overall_status
        }

    except Exception as e:
        data['error'] = str(e)
        data['summary'] = {
            'total_tables': len(get_monitoring_targets()),
            'new_total': 0,
            'recurring_total': 0,
            'total': 0,
            'status': 'error'
        }

    return JsonResponse(data)


def recurring_detail(request):
    """
    특정 테이블의 에러 상품 상세 조회 API
    filter: 'all', 'new', 'recurring'
    """
    date_str = request.GET.get('date')
    table_name = request.GET.get('table')
    error_type = request.GET.get('error_type', 'title_null')
    days = int(request.GET.get('days', 3))
    filter_type = request.GET.get('filter', 'all')  # all, new, recurring
    page = int(request.GET.get('page', 1))
    page_size = int(request.GET.get('page_size', 50))

    if not table_name:
        return JsonResponse({'error': '테이블명을 입력하세요.'})

    valid_tables = [t[0] for t in get_monitoring_targets()]
    if table_name not in valid_tables:
        return JsonResponse({'error': '유효하지 않은 테이블명입니다.'})

    valid_error_types = ['title_null', 'imageurl_null', 'imageurl_invalid', 'partial_null']
    if error_type not in valid_error_types:
        return JsonResponse({'error': '유효하지 않은 에러 타입입니다.'})

    if days < 1:
        days = 1
    elif days > 7:
        days = 7

    if date_str:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    else:
        target_date = (datetime.now() - timedelta(days=1)).date()

    data = {
        'timestamp': datetime.now().isoformat(),
        'date': str(target_date),
        'days': days,
        'table': table_name,
        'error_type': error_type,
        'filter': filter_type,
        'page': page,
        'page_size': page_size,
        'data': []
    }

    try:
        conn = get_ds_connection()
        cursor = conn.cursor()

        # 에러 상품 분석
        analysis = get_error_analysis(cursor, table_name, target_date, days)
        all_products = analysis.get(error_type, {})

        # 필터 적용
        if filter_type == 'new':
            filtered_products = {p: d for p, d in all_products.items() if d == 1}
        elif filter_type == 'recurring':
            filtered_products = {p: d for p, d in all_products.items() if d >= 2}
        else:
            filtered_products = all_products

        # producturl 목록
        product_urls = list(filtered_products.keys())
        total_count = len(product_urls)

        # 페이징
        offset = (page - 1) * page_size
        paged_urls = product_urls[offset:offset + page_size]

        items = []
        if paged_urls:
            # 가장 최근 날짜의 상품 정보 조회
            date_str_fmt = target_date.strftime('%Y%m%d')
            start_datetime = f"{date_str_fmt}0000"
            next_date = (target_date + timedelta(days=1)).strftime('%Y%m%d')
            end_datetime = f"{next_date}0000"

            placeholders = ', '.join(['%s'] * len(paged_urls))
            query = f"""
                SELECT DISTINCT title, retailprice, ships_from, sold_by, imageurl, producturl
                FROM samsung_ds_retail_com.{table_name}
                WHERE crawl_strdatetime >= %s AND crawl_strdatetime < %s
                AND producturl IN ({placeholders})
            """

            cursor.execute(query, [start_datetime, end_datetime] + paged_urls)
            rows = cursor.fetchall()

            for row in rows:
                producturl = row[5] or ''
                recurring_days = filtered_products.get(producturl, 0)
                items.append({
                    'title': row[0] or '',
                    'retailprice': row[1] or '',
                    'ships_from': row[2] or '',
                    'sold_by': row[3] or '',
                    'imageurl': row[4] or '',
                    'producturl': producturl,
                    'recurring_days': recurring_days,
                    'is_new': recurring_days == 1
                })

        cursor.close()
        conn.close()

        retailer_info = next((t for t in get_monitoring_targets() if t[0] == table_name), None)

        data['retailer'] = retailer_info[1] if retailer_info else table_name
        data['region'] = retailer_info[2] if retailer_info else ''
        data['country'] = retailer_info[4].upper() if retailer_info else ''
        data['total_count'] = total_count
        data['total_pages'] = (total_count + page_size - 1) // page_size if total_count > 0 else 1
        data['data'] = items

    except Exception as e:
        data['error'] = str(e)

    return JsonResponse(data)
