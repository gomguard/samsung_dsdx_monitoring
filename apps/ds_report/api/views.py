"""
DS 모니터링 보고 API
- 수집일자별 리테일러 현황
- NULL 필드 특이사항
"""

from django.http import JsonResponse
from datetime import datetime, timedelta
from apps.common.db import get_ds_connection
from config.targets import get_report_targets


def get_monitoring_targets():
    """CSV에서 Report용 모니터링 대상 목록 로드"""
    return get_report_targets()


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
    """예상 수집 건수 조회"""
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


def get_null_issues(cursor, table_name, target_date):
    """
    특정 테이블의 NULL 필드 이슈 조회

    Layer 2 검증 로직 기반 + NULL 필드 조합별로 그룹핑:
    - 모든 NULL 필드 조합을 한 번에 조회
    - title, imageurl, retailprice 중 NULL인 필드들을 조합으로 표시
    - ships_from, sold_by는 retailprice와 함께 3개 모두 NULL이면 정상 (이슈 아님)
    """
    date_str = target_date.strftime('%Y%m%d')
    start_datetime = f"{date_str}0000"
    next_date = (target_date + timedelta(days=1)).strftime('%Y%m%d')
    end_datetime = f"{next_date}0000"

    issues = []

    base_query = f"""
        SELECT DISTINCT * FROM samsung_ds_retail_com.{table_name}
        WHERE crawl_strdatetime >= %s AND crawl_strdatetime < %s
    """

    try:
        # 모든 NULL 필드 조합을 한 번에 조회
        cursor.execute(f"""
            SELECT
                CASE WHEN (title IS NULL OR TRIM(title) = '') THEN 1 ELSE 0 END as title_null,
                CASE WHEN (imageurl IS NULL OR TRIM(imageurl) = '' OR imageurl NOT LIKE 'https://%%') THEN 1 ELSE 0 END as img_null,
                CASE WHEN (retailprice IS NULL OR TRIM(retailprice) = '') THEN 1 ELSE 0 END as rp_null,
                CASE WHEN (ships_from IS NULL OR TRIM(ships_from) = '') THEN 1 ELSE 0 END as sf_null,
                CASE WHEN (sold_by IS NULL OR TRIM(sold_by) = '') THEN 1 ELSE 0 END as sb_null,
                COUNT(*) as cnt
            FROM ({base_query}) A
            GROUP BY
                CASE WHEN (title IS NULL OR TRIM(title) = '') THEN 1 ELSE 0 END,
                CASE WHEN (imageurl IS NULL OR TRIM(imageurl) = '' OR imageurl NOT LIKE 'https://%%') THEN 1 ELSE 0 END,
                CASE WHEN (retailprice IS NULL OR TRIM(retailprice) = '') THEN 1 ELSE 0 END,
                CASE WHEN (ships_from IS NULL OR TRIM(ships_from) = '') THEN 1 ELSE 0 END,
                CASE WHEN (sold_by IS NULL OR TRIM(sold_by) = '') THEN 1 ELSE 0 END
        """, (start_datetime, end_datetime))

        for row in cursor.fetchall():
            title_null, img_null, rp_null, sf_null, sb_null, count = row

            # 모두 정상인 경우 스킵
            if title_null == 0 and img_null == 0 and rp_null == 0 and sf_null == 0 and sb_null == 0:
                continue

            # title, imageurl이 유효하고 retailprice, ships_from, sold_by 3개 모두 NULL인 경우는 정상
            if title_null == 0 and img_null == 0 and rp_null == 1 and sf_null == 1 and sb_null == 1:
                continue

            # NULL 필드 조합 생성
            null_fields = []
            if title_null:
                null_fields.append('title')
            if img_null:
                null_fields.append('imageurl')
            if rp_null:
                null_fields.append('retailprice')
            # ships_from, sold_by는 부분 NULL일 때만 표시 (title/imageurl 유효한 경우)
            if title_null == 0 and img_null == 0:
                if sf_null and not (rp_null and sb_null):  # 부분 NULL
                    null_fields.append('ships_from')
                if sb_null and not (rp_null and sf_null):  # 부분 NULL
                    null_fields.append('sold_by')

            if null_fields and count > 0:
                issues.append({'fields': ', '.join(null_fields), 'count': count})

    except Exception as e:
        pass

    return issues


def get_duplicate_count(cursor, table_name, target_date):
    """특정 테이블의 중복 건수 조회 (같은 product_name이 2번 이상)"""
    date_str = target_date.strftime('%Y%m%d')
    start_datetime = f"{date_str}0000"
    next_date = (target_date + timedelta(days=1)).strftime('%Y%m%d')
    end_datetime = f"{next_date}0000"

    try:
        query = f"""
            SELECT COUNT(*) FROM (
                SELECT product_name, COUNT(*) as cnt
                FROM samsung_ds_retail_com.{table_name}
                WHERE crawl_strdatetime >= %s AND crawl_strdatetime < %s
                AND product_name IS NOT NULL AND TRIM(product_name) != ''
                GROUP BY product_name
                HAVING COUNT(*) > 1
            ) dup
        """
        cursor.execute(query, (start_datetime, end_datetime))
        return cursor.fetchone()[0] or 0
    except Exception as e:
        return 0


def report_stats(request):
    """DS 모니터링 보고용 통계 API"""
    date_str = request.GET.get('date')

    if date_str:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    else:
        target_date = (datetime.now() - timedelta(days=1)).date()

    data = {
        'timestamp': datetime.now().isoformat(),
        'date': str(target_date),
        'retailers': [],
        'issues': [],
        'summary': {}
    }

    try:
        conn = get_ds_connection()
        cursor = conn.cursor()

        retailers = []
        all_issues = []

        for table_name, retailer_name, country, mall_name in get_monitoring_targets():
            expected = get_expected_count(cursor, country, mall_name)
            actual = get_crawl_count(cursor, table_name, target_date)

            retailers.append({
                'name': retailer_name,
                'actual': actual,
                'expected': expected,
                'table_name': table_name
            })

            # NULL 이슈 체크 (Layer 2 검증 로직과 동일)
            null_issues = get_null_issues(cursor, table_name, target_date)
            for issue in null_issues:
                all_issues.append({
                    'retailer': retailer_name,
                    'type': 'null',
                    'description': f"{issue['fields']} null {issue['count']}건"
                })

            # 중복 체크 (다나와만)
            if mall_name == 'danawa':
                dup_count = get_duplicate_count(cursor, table_name, target_date)
                if dup_count > 0:
                    all_issues.append({
                        'retailer': retailer_name,
                        'type': 'duplicate',
                        'description': f'같은제품 {dup_count}건 중복 저장',
                        'count': dup_count
                    })

        cursor.close()
        conn.close()

        # 정상 수집 여부 판단
        success_count = sum(1 for r in retailers if r['actual'] >= r['expected'] and r['expected'] > 0)

        data['retailers'] = retailers
        data['issues'] = all_issues
        data['summary'] = {
            'total_retailers': len(get_monitoring_targets()),
            'success_count': success_count,
            'issue_count': len(all_issues)
        }

    except Exception as e:
        data['error'] = str(e)
        data['summary'] = {
            'total_retailers': len(get_monitoring_targets()),
            'success_count': 0,
            'issue_count': 0
        }

    return JsonResponse(data)


def report_detail(request):
    """리테일러별 상세 정보 API"""
    date_str = request.GET.get('date')
    retailer = request.GET.get('retailer', '')

    if date_str:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    else:
        target_date = (datetime.now() - timedelta(days=1)).date()

    # 리테일러 테이블 찾기
    table_info = None
    for table_name, retailer_name, country, mall_name in get_monitoring_targets():
        if retailer_name == retailer:
            table_info = (table_name, retailer_name, country, mall_name)
            break

    if not table_info:
        return JsonResponse({'error': '리테일러를 찾을 수 없습니다.'})

    table_name, retailer_name, country, mall_name = table_info
    date_str_fmt = target_date.strftime('%Y%m%d')
    start_datetime = f"{date_str_fmt}0000"
    next_date = (target_date + timedelta(days=1)).strftime('%Y%m%d')
    end_datetime = f"{next_date}0000"

    data = {
        'date': str(target_date),
        'retailer': retailer_name,
        'null_records': [],
        'duplicate_records': []
    }

    try:
        conn = get_ds_connection()
        cursor = conn.cursor()

        # NULL 레코드 조회 (title, retailprice, imageurl 중 하나라도 NULL인 것)
        query = f"""
            SELECT product_name, title, retailprice, imageurl, crawl_strdatetime
            FROM samsung_ds_retail_com.{table_name}
            WHERE crawl_strdatetime >= %s AND crawl_strdatetime < %s
            AND (
                title IS NULL OR TRIM(title) = ''
                OR retailprice IS NULL OR TRIM(retailprice) = ''
                OR imageurl IS NULL OR TRIM(imageurl) = ''
            )
            ORDER BY crawl_strdatetime DESC
            LIMIT 100
        """
        cursor.execute(query, (start_datetime, end_datetime))
        rows = cursor.fetchall()

        for row in rows:
            null_fields = []
            if not row[1] or not row[1].strip():
                null_fields.append('title')
            if not row[2] or not row[2].strip():
                null_fields.append('retailprice')
            if not row[3] or not row[3].strip():
                null_fields.append('imageurl')

            data['null_records'].append({
                'product_name': row[0],
                'title': row[1],
                'retailprice': row[2],
                'imageurl': row[3],
                'crawl_datetime': row[4],
                'null_fields': null_fields
            })

        # 중복 레코드 조회 (다나와만)
        if mall_name == 'danawa':
            query = f"""
                SELECT product_name, COUNT(*) as cnt
                FROM samsung_ds_retail_com.{table_name}
                WHERE crawl_strdatetime >= %s AND crawl_strdatetime < %s
                AND product_name IS NOT NULL AND TRIM(product_name) != ''
                GROUP BY product_name
                HAVING COUNT(*) > 1
                ORDER BY COUNT(*) DESC
                LIMIT 50
            """
            cursor.execute(query, (start_datetime, end_datetime))
            dup_rows = cursor.fetchall()

            for row in dup_rows:
                data['duplicate_records'].append({
                    'product_name': row[0],
                    'count': row[1]
                })

        cursor.close()
        conn.close()

    except Exception as e:
        data['error'] = str(e)

    return JsonResponse(data)
