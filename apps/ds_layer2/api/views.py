"""
DS Layer 2 API: 데이터 품질 검수 (NULL 필드 체크)
날짜별 NULL 필드 현황 조회 API

검증 조건:
1. title이 NULL이거나 imageurl이 'https://'로 시작하지 않으면 → 기본 필드 NULL
2. title과 imageurl이 둘 다 유효할 때:
   - retailprice, ships_from, sold_by 3개 모두 NULL → 정상
   - retailprice, ships_from, sold_by 일부만 NULL → 비정상 (부분 NULL)
"""

import json
import traceback
import paramiko
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from datetime import datetime, timedelta
from apps.common.db import get_ds_connection
from apps.common.targets import load_monitoring_targets, format_time
from config.config import FILE_SERVER_CONFIG


def log_error(func_name, error):
    """공통 에러 로깅 함수"""
    print(f"[DB ERROR] {func_name}: {error}")
    traceback.print_exc()


def get_monitoring_targets():
    """CSV에서 모니터링 대상 목록 로드"""
    return load_monitoring_targets()


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
        log_error('get_batches_for_date', e)

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
        log_error('get_expected_count', e)
        return 0


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
        'title_null': 0,  # title이 NULL인 건 (imageurl 상관없이)
        'imageurl_null': 0,  # imageurl이 NULL인 건 (title 상관없이)
        'null_union': 0,  # title NULL 또는 imageurl NULL (중복 제외)
        'imageurl_invalid': 0,  # imageurl이 있지만 형식 오류
        'price_zero': 0,  # retailprice가 0원인 건
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

        # 2. title NULL 건수 (imageurl 상관없이)
        cursor.execute(f"""
            SELECT COUNT(*) FROM ({base_query}) A
            WHERE title IS NULL OR TRIM(title) = ''
        """, (start_datetime, end_datetime))
        results['title_null'] = cursor.fetchone()[0] or 0

        # 3. imageurl NULL 건수 (title 상관없이)
        cursor.execute(f"""
            SELECT COUNT(*) FROM ({base_query}) A
            WHERE imageurl IS NULL OR TRIM(imageurl) = ''
        """, (start_datetime, end_datetime))
        results['imageurl_null'] = cursor.fetchone()[0] or 0

        # 4. title NULL 또는 imageurl NULL (중복 제외한 합집합)
        cursor.execute(f"""
            SELECT COUNT(*) FROM ({base_query}) A
            WHERE (title IS NULL OR TRIM(title) = '')
            OR (imageurl IS NULL OR TRIM(imageurl) = '')
        """, (start_datetime, end_datetime))
        results['null_union'] = cursor.fetchone()[0] or 0

        # 4. imageurl 무효 건수 (title 유효, imageurl이 있지만 https://로 시작하지 않음)
        cursor.execute(f"""
            SELECT COUNT(*) FROM ({base_query}) A
            WHERE (title IS NOT NULL AND TRIM(title) != '')
            AND (imageurl IS NOT NULL AND TRIM(imageurl) != '')
            AND imageurl NOT LIKE 'https://%%'
        """, (start_datetime, end_datetime))
        results['imageurl_invalid'] = cursor.fetchone()[0] or 0

        # 5. retailprice 0원 (title 유효, retailprice가 0 또는 $0, $0.00 등)
        cursor.execute(f"""
            SELECT COUNT(*) FROM ({base_query}) A
            WHERE (title IS NOT NULL AND TRIM(title) != '')
            AND (retailprice = '0' OR retailprice REGEXP '^\\\\$?0(\\\\.0+)?$')
        """, (start_datetime, end_datetime))
        results['price_zero'] = cursor.fetchone()[0] or 0

        # 6. title과 imageurl이 둘 다 유효한 데이터 중에서 검사
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
        log_error('get_quality_counts', e)
        results['error'] = str(e)

    return results


def get_quality_counts_by_time_range(cursor, table_name, target_date, start_time, end_time):
    """
    특정 시간 범위 내의 데이터 품질 현황 조회
    start_time, end_time: 'HH:MM' 형식
    end_time이 None이면 다음날 00:00까지
    """
    date_str = target_date.strftime('%Y%m%d')
    start_datetime = f"{date_str}{start_time.replace(':', '')}00"

    if end_time:
        end_datetime = f"{date_str}{end_time.replace(':', '')}00"
    else:
        next_date = (target_date + timedelta(days=1)).strftime('%Y%m%d')
        end_datetime = f"{next_date}0000"

    results = {
        'total': 0,
        'title_null': 0,
        'imageurl_null': 0,
        'null_union': 0,
        'imageurl_invalid': 0,
        'price_zero': 0,
        'partial_null': 0,
        'all_null': 0,
        'valid': 0,
    }

    try:
        base_query = f"""
            SELECT DISTINCT * FROM samsung_ds_retail_com.{table_name}
            WHERE crawl_strdatetime >= %s AND crawl_strdatetime < %s
        """

        # 전체 건수
        cursor.execute(f"SELECT COUNT(*) FROM ({base_query}) A", (start_datetime, end_datetime))
        results['total'] = cursor.fetchone()[0] or 0

        # title NULL 건수 (imageurl 상관없이)
        cursor.execute(f"""
            SELECT COUNT(*) FROM ({base_query}) A
            WHERE title IS NULL OR TRIM(title) = ''
        """, (start_datetime, end_datetime))
        results['title_null'] = cursor.fetchone()[0] or 0

        # imageurl NULL 건수 (title 상관없이)
        cursor.execute(f"""
            SELECT COUNT(*) FROM ({base_query}) A
            WHERE imageurl IS NULL OR TRIM(imageurl) = ''
        """, (start_datetime, end_datetime))
        results['imageurl_null'] = cursor.fetchone()[0] or 0

        # title NULL 또는 imageurl NULL (중복 제외)
        cursor.execute(f"""
            SELECT COUNT(*) FROM ({base_query}) A
            WHERE (title IS NULL OR TRIM(title) = '')
            OR (imageurl IS NULL OR TRIM(imageurl) = '')
        """, (start_datetime, end_datetime))
        results['null_union'] = cursor.fetchone()[0] or 0

        # imageurl 무효 (title 유효, imageurl이 있지만 https://로 시작하지 않음)
        cursor.execute(f"""
            SELECT COUNT(*) FROM ({base_query}) A
            WHERE (title IS NOT NULL AND TRIM(title) != '')
            AND (imageurl IS NOT NULL AND TRIM(imageurl) != '')
            AND imageurl NOT LIKE 'https://%%'
        """, (start_datetime, end_datetime))
        results['imageurl_invalid'] = cursor.fetchone()[0] or 0

        # retailprice 0원 (title 유효, retailprice가 0 또는 $0, $0.00 등)
        cursor.execute(f"""
            SELECT COUNT(*) FROM ({base_query}) A
            WHERE (title IS NOT NULL AND TRIM(title) != '')
            AND (retailprice = '0' OR retailprice REGEXP '^\\\\$?0(\\\\.0+)?$')
        """, (start_datetime, end_datetime))
        results['price_zero'] = cursor.fetchone()[0] or 0

        # title과 imageurl이 둘 다 유효한 데이터 중에서 검사
        valid_base = f"""
            SELECT * FROM ({base_query}) A
            WHERE (title IS NOT NULL AND TRIM(title) != '')
            AND (imageurl IS NOT NULL AND imageurl LIKE 'https://%%')
        """

        # 3개 필드 모두 NULL (정상)
        cursor.execute(f"""
            SELECT COUNT(*) FROM ({valid_base}) B
            WHERE (retailprice IS NULL OR TRIM(retailprice) = '')
            AND (ships_from IS NULL OR TRIM(ships_from) = '')
            AND (sold_by IS NULL OR TRIM(sold_by) = '')
        """, (start_datetime, end_datetime))
        results['all_null'] = cursor.fetchone()[0] or 0

        # 부분 NULL (title/imageurl 유효, retailprice/ships_from/sold_by 중 일부만 NULL)
        cursor.execute(f"""
            SELECT COUNT(*) FROM ({valid_base}) B
            WHERE NOT (
                ((retailprice IS NOT NULL AND TRIM(retailprice) != '')
                 AND (ships_from IS NOT NULL AND TRIM(ships_from) != '')
                 AND (sold_by IS NOT NULL AND TRIM(sold_by) != ''))
                OR
                ((retailprice IS NULL OR TRIM(retailprice) = '')
                 AND (ships_from IS NULL OR TRIM(ships_from) = '')
                 AND (sold_by IS NULL OR TRIM(sold_by) = ''))
            )
        """, (start_datetime, end_datetime))
        results['partial_null'] = cursor.fetchone()[0] or 0

        # 완전히 정상 (title, imageurl 유효 + 3개 필드 모두 유효)
        cursor.execute(f"""
            SELECT COUNT(*) FROM ({valid_base}) B
            WHERE (retailprice IS NOT NULL AND TRIM(retailprice) != '')
            AND (ships_from IS NOT NULL AND TRIM(ships_from) != '')
            AND (sold_by IS NOT NULL AND TRIM(sold_by) != '')
        """, (start_datetime, end_datetime))
        results['valid'] = cursor.fetchone()[0] or 0

    except Exception as e:
        log_error('get_quality_counts_by_time_range', e)
        results['error'] = str(e)

    return results


def layer_stats(request):
    """DS Layer 2 전체 데이터 품질 통계 API"""
    date_str = request.GET.get('date')
    batch_view = request.GET.get('batch_view', 'final')  # 'final' or 'all'

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

        # 배치 정보 로드
        batches_by_retailer = get_batches_for_date(target_date)

        results = []
        total_records = 0
        total_title_null = 0
        total_imageurl_null = 0
        total_null_union = 0
        total_imageurl_invalid = 0
        total_price_zero = 0
        total_partial_null = 0
        total_all_null = 0
        total_valid = 0

        for idx, (table_name, retailer, region, korea_time, country, mall_name) in enumerate(get_monitoring_targets(), 1):
            retailer_batches = batches_by_retailer.get(retailer, [])

            # 배치가 2개 이상이고 'final' 뷰인 경우, 마지막 배치만 조회
            final_start_time = None
            final_end_time = None
            if len(retailer_batches) >= 2 and batch_view == 'final':
                last_batch = retailer_batches[-1]
                final_start_time = last_batch['start_time']
                final_end_time = None  # 다음날까지
                quality = get_quality_counts_by_time_range(cursor, table_name, target_date, final_start_time, final_end_time)
            else:
                quality = get_quality_counts(cursor, table_name, target_date)

            total = quality.get('total', 0)
            total_records += total

            # 예상 수집 건수 조회 (Layer 1 samsung_price_tracking_list)
            expected_count = get_expected_count(cursor, country, mall_name)

            title_null = quality.get('title_null', 0)
            imageurl_null = quality.get('imageurl_null', 0)
            null_union = quality.get('null_union', 0)
            imageurl_invalid = quality.get('imageurl_invalid', 0)
            price_zero = quality.get('price_zero', 0)
            partial_null = quality.get('partial_null', 0)
            all_null = quality.get('all_null', 0)
            valid = quality.get('valid', 0)

            total_title_null += title_null
            total_imageurl_null += imageurl_null
            total_null_union += null_union
            total_imageurl_invalid += imageurl_invalid
            total_price_zero += price_zero
            total_partial_null += partial_null
            total_all_null += all_null
            total_valid += valid

            # 비정상 건수 = null_union (중복 제외) + imageurl 무효 + 0원 + 부분 NULL
            error_count = null_union + imageurl_invalid + price_zero + partial_null

            # 상태 판정
            if total == 0:
                status = 'pending'
            elif error_count == 0:
                status = 'success'
            elif error_count < total * 0.05:  # 5% 미만
                status = 'warning'
            else:
                status = 'danger'

            # 배치 정보 처리
            batch_count = len(retailer_batches)  # 총 배치 수 (재실행 횟수 = batch_count - 1)
            has_multi_batch = batch_count >= 2 and batch_view == 'all'
            batch_details = []

            if has_multi_batch:
                # 각 배치별 품질 현황 계산
                for i, batch in enumerate(retailer_batches):
                    start_time = batch['start_time']
                    # 다음 배치의 시작시간이 이 배치의 종료시간
                    if i + 1 < len(retailer_batches):
                        end_time = retailer_batches[i + 1]['start_time']
                    else:
                        end_time = None  # 마지막 배치는 다음날 00:00까지

                    batch_quality = get_quality_counts_by_time_range(cursor, table_name, target_date, start_time, end_time)
                    batch_error = batch_quality.get('error_count', 0)

                    batch_details.append({
                        'id': batch['id'],
                        'start_time': start_time,
                        'end_time': end_time if end_time else '다음날',
                        'memo': batch['memo'],
                        'total': batch_quality.get('total', 0),
                        'null_union': batch_quality.get('null_union', 0),
                        'imageurl_invalid': batch_quality.get('imageurl_invalid', 0),
                        'partial_null': batch_quality.get('partial_null', 0),
                        'error_count': batch_error
                    })

            results.append({
                'no': idx,
                'table_name': table_name,
                'retailer': retailer,
                'region': region,
                'country': country,
                'mall_name': mall_name,
                'total': total,
                'expected_count': expected_count,
                'title_null': title_null,
                'imageurl_null': imageurl_null,
                'null_union': null_union,
                'imageurl_invalid': imageurl_invalid,
                'price_zero': price_zero,
                'partial_null': partial_null,
                'all_null': all_null,
                'valid': valid,
                'error_count': error_count,
                'status': status,
                'batch_count': batch_count,
                'has_multi_batch': has_multi_batch,
                'batches': batch_details,
                'final_start_time': final_start_time,
                'final_end_time': final_end_time
            })

        cursor.close()
        conn.close()

        # 전체 비정상 건수 = null_union (중복 제외) + imageurl 무효 + 0원 + 부분 NULL
        total_error = total_null_union + total_imageurl_invalid + total_price_zero + total_partial_null

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
            'total_tables': len(get_monitoring_targets()),
            'total_records': total_records,
            'title_null': total_title_null,
            'imageurl_null': total_imageurl_null,
            'null_union': total_null_union,
            'imageurl_invalid': total_imageurl_invalid,
            'price_zero': total_price_zero,
            'partial_null': total_partial_null,
            'all_null': total_all_null,
            'valid': total_valid,
            'total_error': total_error,
            'status': overall_status
        }

    except Exception as e:
        log_error('layer_stats', e)
        data['error'] = str(e)
        data['summary'] = {
            'total_tables': len(get_monitoring_targets()),
            'total_records': 0,
            'total_error': 0,
            'status': 'error'
        }

    return JsonResponse(data)


def table_null_detail(request):
    """
    특정 테이블의 비정상 데이터 상세 조회 API

    error_type:
    - title_null: title이 NULL인 데이터 (imageurl 상관없이)
    - imageurl_null: imageurl이 NULL인 데이터 (title 상관없이)
    - imageurl_invalid: title 유효, imageurl이 있지만 형식 오류
    - partial_null: title/imageurl 유효, retailprice/ships_from/sold_by 일부만 NULL
    """
    date_str = request.GET.get('date')
    table_name = request.GET.get('table')
    error_type = request.GET.get('error_type', 'title_null')
    page = int(request.GET.get('page', 1))
    page_size = int(request.GET.get('page_size', 50))

    # 시간 범위 파라미터 (배치별 상세보기)
    start_time = request.GET.get('start_time')
    end_time = request.GET.get('end_time')

    # 정렬 파라미터
    sort_by = request.GET.get('sort_by', 'crawl_strdatetime')
    sort_order = request.GET.get('sort_order', 'asc')

    if not table_name:
        return JsonResponse({'error': '테이블명을 입력하세요.'})

    valid_tables = [t[0] for t in get_monitoring_targets()]
    if table_name not in valid_tables:
        return JsonResponse({'error': '유효하지 않은 테이블명입니다.'})

    valid_error_types = ['title_null', 'imageurl_null', 'imageurl_invalid', 'price_zero', 'partial_null']
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

        # 시간 범위 처리 (배치별 상세보기)
        if start_time:
            start_datetime = f"{date_str_fmt}{start_time.replace(':', '')}00"
        else:
            start_datetime = f"{date_str_fmt}0000"

        if end_time and end_time != '다음날':
            end_datetime = f"{date_str_fmt}{end_time.replace(':', '')}00"
        else:
            next_date = (target_date + timedelta(days=1)).strftime('%Y%m%d')
            end_datetime = f"{next_date}0000"

        # 정렬 컬럼 검증
        valid_sort_columns = ['crawl_strdatetime', 'title', 'retailprice', 'ships_from', 'sold_by']
        if sort_by not in valid_sort_columns:
            sort_by = 'crawl_strdatetime'
        sort_direction = 'DESC' if sort_order.lower() == 'desc' else 'ASC'

        base_query = f"""
            SELECT DISTINCT * FROM samsung_ds_retail_com.{table_name}
            WHERE crawl_strdatetime >= %s AND crawl_strdatetime < %s
        """

        # 에러 타입별 WHERE 조건
        if error_type == 'title_null':
            where_condition = "WHERE title IS NULL OR TRIM(title) = ''"
        elif error_type == 'imageurl_null':
            where_condition = "WHERE imageurl IS NULL OR TRIM(imageurl) = ''"
        elif error_type == 'imageurl_invalid':
            where_condition = """
                WHERE (title IS NOT NULL AND TRIM(title) != '')
                AND (imageurl IS NOT NULL AND TRIM(imageurl) != '')
                AND imageurl NOT LIKE 'https://%%'
            """
        elif error_type == 'price_zero':
            where_condition = """
                WHERE (title IS NOT NULL AND TRIM(title) != '')
                AND (retailprice = '0' OR retailprice REGEXP '^\\\\$?0(\\\\.0+)?$')
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
            SELECT title, retailprice, ships_from, sold_by, imageurl, producturl, crawl_strdatetime
            FROM ({base_query}) A
            {where_condition}
            ORDER BY {sort_by} {sort_direction}
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

        cursor.close()
        conn.close()

        retailer_info = next((t for t in get_monitoring_targets() if t[0] == table_name), None)

        data['retailer'] = retailer_info[1] if retailer_info else table_name
        data['region'] = retailer_info[2] if retailer_info else ''
        data['country'] = retailer_info[4] if retailer_info else ''
        data['total_count'] = total_count
        data['total_pages'] = (total_count + page_size - 1) // page_size if total_count > 0 else 1
        data['data'] = items
        data['sort_by'] = sort_by
        data['sort_order'] = sort_order
        if start_time:
            data['time_range'] = f"{start_time} ~ {end_time if end_time else '다음날'}"

    except Exception as e:
        log_error('table_null_detail', e)
        data['error'] = str(e)

    return JsonResponse(data)


def get_file_info_for_date(target_date):
    """
    특정 날짜의 리테일러별 파일 정보 조회 (SFTP)
    반환: {retailer_name: {'file_name': str, 'file_size': int}, ...}
    """
    date_folder = target_date.strftime('%Y%m%d')
    file_info = {}

    try:
        transport = paramiko.Transport((FILE_SERVER_CONFIG['host'], FILE_SERVER_CONFIG['port']))
        transport.connect(
            username=FILE_SERVER_CONFIG['username'],
            password=FILE_SERVER_CONFIG['password']
        )
        sftp = paramiko.SFTPClient.from_transport(transport)
        base_path = FILE_SERVER_CONFIG['upload_path']

        # 리테일러명 매핑 (country_retailer -> retailer_name)
        # 파일서버 파일명에는 '-'가 없으므로 제거하여 매핑 (예: x-kom -> xkom)
        targets = get_monitoring_targets()
        retailer_map = {}
        for t in targets:
            country = t[4].lower() if t[4] else ''
            mall = t[5].lower().replace(' ', '_').replace('-', '') if t[5] else ''
            key = f"{country}_{mall}"
            retailer_map[key] = t[1]  # retailer name

        # 국가별 디렉토리 조회
        try:
            country_dirs = sftp.listdir(base_path)
        except Exception:
            country_dirs = []

        for country_code in country_dirs:
            country_path = f"{base_path}/{country_code}"

            try:
                stat = sftp.stat(country_path)
                if not (stat.st_mode & 0o40000):
                    continue
            except Exception:
                continue

            date_path = f"{country_path}/{date_folder}"
            try:
                sftp.stat(date_path)
            except FileNotFoundError:
                continue

            try:
                files = sftp.listdir_attr(date_path)
                zip_files = [f for f in files if f.filename.endswith('.zip') and not (f.st_mode & 0o40000)]

                for f in zip_files:
                    filename = f.filename
                    parts = filename.replace('.zip', '').split('_')
                    if len(parts) >= 4:
                        file_country = parts[2]
                        file_retailer = '_'.join(parts[3:])
                        retailer_key = f"{file_country}_{file_retailer}"
                        retailer_name = retailer_map.get(retailer_key, file_retailer)
                    else:
                        retailer_name = country_code.upper()

                    file_info[retailer_name] = {
                        'file_name': filename,
                        'file_size': f.st_size
                    }
            except Exception:
                continue

        sftp.close()
        transport.close()

    except Exception as e:
        log_error('get_file_info_for_date', e)

    return file_info


def get_retailer_stats(cursor, retailer, target_date, file_info_cache=None, include_file_info=True):
    """
    리테일러의 통계 데이터 계산 (공통 함수)
    - expected_count: 예상 수집 건수
    - total_count: 하루 전체 수집 건수
    - final_batch_count: 최종 배치 건수
    - completion_rate: 완료율
    - rerun_count: 재실행 횟수
    - 이상치 통계 (최종 배치 기준)
    - file_name, file_size: include_file_info=True일 때만 file_info_cache에서 조회
    """
    # 리테일러 타겟 정보 찾기
    all_targets = get_monitoring_targets()
    target_info = None
    for t in all_targets:
        if t[1] == retailer:
            target_info = t
            break

    if not target_info:
        return None

    table_name = target_info[0]
    country = target_info[4]
    mall_name = target_info[5]

    # 배치 정보 조회
    batches_by_retailer = get_batches_for_date(target_date)
    retailer_batches = batches_by_retailer.get(retailer, [])
    batch_count = len(retailer_batches)
    rerun_count = max(0, batch_count - 1)

    # 하루 전체 수집 건수 조회
    total_quality = get_quality_counts(cursor, table_name, target_date)
    total_count = total_quality.get('total', 0)

    # 최종 배치 건수 및 이상치 통계 조회
    if batch_count >= 2:
        last_batch = retailer_batches[-1]
        final_quality = get_quality_counts_by_time_range(cursor, table_name, target_date, last_batch['start_time'], None)
        final_batch_count = final_quality.get('total', 0)
        quality = final_quality
    else:
        final_batch_count = total_count
        quality = total_quality

    expected_count = get_expected_count(cursor, country, mall_name)
    completion_rate = round((final_batch_count / expected_count * 100), 2) if expected_count > 0 else 0

    # 이상치 통계 (최종 배치 기준)
    null_union = quality.get('null_union', 0)
    imageurl_invalid = quality.get('imageurl_invalid', 0)
    price_zero = quality.get('price_zero', 0)
    partial_null = quality.get('partial_null', 0)
    anomaly_total = null_union + imageurl_invalid + price_zero + partial_null

    # 파일 정보 조회 (include_file_info=True일 때만)
    file_name = ''
    file_size = 0
    if include_file_info:
        if file_info_cache is None:
            file_info_cache = get_file_info_for_date(target_date)
        retailer_file = file_info_cache.get(retailer, {})
        file_name = retailer_file.get('file_name', '')
        file_size = retailer_file.get('file_size', 0)

    return {
        'expected_count': expected_count,
        'total_count': total_count,
        'final_batch_count': final_batch_count,
        'completion_rate': completion_rate,
        'rerun_count': rerun_count,
        'anomaly_total': anomaly_total,
        'anomaly_title_null': null_union,
        'anomaly_image_null': quality.get('imageurl_null', 0),
        'anomaly_partial_null': partial_null,
        'anomaly_price_zero': price_zero,
        'file_name': file_name,
        'file_size': file_size
    }


@csrf_exempt
@require_http_methods(["POST"])
def report_save(request):
    """
    리테일러별 이상치 데이터 저장 API

    POST 파라미터:
    - crawl_date: 수집일자 (YYYY-MM-DD)
    - retailer: 리테일러명
    - anomalies: 이상치 데이터 목록 (JSON 배열)
    - memo: 메모 (선택)
    """
    try:
        body = json.loads(request.body)
        crawl_date = body.get('crawl_date')
        retailer = body.get('retailer')
        anomalies = body.get('anomalies', [])
        memo = body.get('memo', '')
        user_id = body.get('user_id', 'system')

        if not crawl_date or not retailer:
            return JsonResponse({'success': False, 'error': '필수 파라미터가 누락되었습니다.'})

        conn = get_ds_connection()
        cursor = conn.cursor()
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # 통계 데이터 계산 (백엔드에서 직접, 파일 정보 제외)
        target_date = datetime.strptime(crawl_date, '%Y-%m-%d').date()
        stats = get_retailer_stats(cursor, retailer, target_date, include_file_info=False)
        if not stats:
            cursor.close()
            conn.close()
            return JsonResponse({'success': False, 'error': f'{retailer} 타겟 정보를 찾을 수 없습니다.'})

        # 1. 기존 데이터 soft delete (is_del = 1)
        cursor.execute("""
            UPDATE ssd_crawl_db.ds_monitoring_report_daily
            SET is_del = 1, updated_at = %s, updated_id = %s
            WHERE crawl_date = %s AND retailer = %s AND is_del = 0
        """, (now, user_id, crawl_date, retailer))

        cursor.execute("""
            UPDATE ssd_crawl_db.ds_monitoring_report_anomaly
            SET is_del = 1, updated_at = %s, updated_id = %s
            WHERE crawl_date = %s AND retailer = %s AND is_del = 0
        """, (now, user_id, crawl_date, retailer))

        # 2. report_daily INSERT (파일 정보는 별도 API에서 저장)
        cursor.execute("""
            INSERT INTO ssd_crawl_db.ds_monitoring_report_daily (
                crawl_date, retailer, expected_count, final_batch_count, total_count,
                completion_rate, rerun_count, file_name, file_size,
                anomaly_total, anomaly_title_null, anomaly_image_null,
                anomaly_partial_null, anomaly_price_zero,
                memo, is_closed, is_del, created_at, created_id
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, '', 0, %s, %s, %s, %s, %s, %s, 0, 0, %s, %s
            )
        """, (
            crawl_date, retailer,
            stats['expected_count'],
            stats['final_batch_count'],
            stats['total_count'],
            stats['completion_rate'],
            stats['rerun_count'],
            stats['anomaly_total'],
            stats['anomaly_title_null'],
            stats['anomaly_image_null'],
            stats['anomaly_partial_null'],
            stats['anomaly_price_zero'],
            memo,
            now, user_id
        ))

        report_daily_id = cursor.lastrowid

        # 3. report_anomaly INSERT (각 이상치 데이터)
        anomaly_ids = []
        for anomaly in anomalies:
            cursor.execute("""
                INSERT INTO ssd_crawl_db.ds_monitoring_report_anomaly (
                    crawl_date, retailer, country_code, title, retailprice,
                    ships_from, sold_by, imageurl, producturl,
                    screenshot_id, cause, memo, is_del, created_at, created_id
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 0, %s, %s
                )
            """, (
                crawl_date, retailer,
                anomaly.get('country_code', ''),
                anomaly.get('title', ''),
                anomaly.get('retailprice'),
                anomaly.get('ships_from', ''),
                anomaly.get('sold_by', ''),
                anomaly.get('imageurl', ''),
                anomaly.get('producturl', ''),
                anomaly.get('screenshot_id'),
                anomaly.get('cause', ''),
                anomaly.get('memo', ''),
                now, user_id
            ))
            anomaly_ids.append(cursor.lastrowid)

        conn.commit()
        cursor.close()
        conn.close()

        return JsonResponse({
            'success': True,
            'message': f'{retailer} 저장 완료',
            'report_daily_id': report_daily_id,
            'anomaly_count': len(anomaly_ids),
            'anomaly_ids': anomaly_ids
        })

    except Exception as e:
        log_error('report_save', e)
        return JsonResponse({'success': False, 'error': str(e)})


@csrf_exempt
@require_http_methods(["POST"])
def report_delete(request):
    """
    리테일러별 저장된 데이터 삭제 API (soft delete)

    POST 파라미터:
    - crawl_date: 수집일자 (YYYY-MM-DD)
    - retailer: 리테일러명
    """
    try:
        body = json.loads(request.body)
        crawl_date = body.get('crawl_date')
        retailer = body.get('retailer')
        user_id = body.get('user_id', 'system')

        if not crawl_date or not retailer:
            return JsonResponse({'success': False, 'error': '필수 파라미터가 누락되었습니다.'})

        conn = get_ds_connection()
        cursor = conn.cursor()
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # report_daily soft delete
        cursor.execute("""
            UPDATE ssd_crawl_db.ds_monitoring_report_daily
            SET is_del = 1, updated_at = %s, updated_id = %s
            WHERE crawl_date = %s AND retailer = %s AND is_del = 0
        """, (now, user_id, crawl_date, retailer))
        daily_deleted = cursor.rowcount

        # report_anomaly soft delete
        cursor.execute("""
            UPDATE ssd_crawl_db.ds_monitoring_report_anomaly
            SET is_del = 1, updated_at = %s, updated_id = %s
            WHERE crawl_date = %s AND retailer = %s AND is_del = 0
        """, (now, user_id, crawl_date, retailer))
        anomaly_deleted = cursor.rowcount

        conn.commit()
        cursor.close()
        conn.close()

        return JsonResponse({
            'success': True,
            'message': f'{retailer} 삭제 완료',
            'daily_deleted': daily_deleted,
            'anomaly_deleted': anomaly_deleted
        })

    except Exception as e:
        log_error('report_delete', e)
        return JsonResponse({'success': False, 'error': str(e)})


@csrf_exempt
@require_http_methods(["POST"])
def report_update(request):
    """
    이상치 데이터 수정 API (cause, memo, screenshot_id) - 단건 또는 일괄

    POST 파라미터 (단건):
    - anomaly_id: 이상치 ID
    - cause: 원인 (선택)
    - memo: 메모 (선택)
    - screenshot_id: 스크린샷 파일 ID (선택)

    POST 파라미터 (일괄):
    - updates: [{anomaly_id, cause, memo}, ...] 배열
    """
    try:
        body = json.loads(request.body)
        user_id = body.get('user_id', 'system')

        conn = get_ds_connection()
        cursor = conn.cursor()
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # 일괄 처리
        if 'updates' in body:
            updates = body['updates']
            if not updates or not isinstance(updates, list):
                return JsonResponse({'success': False, 'error': 'updates 배열이 필요합니다.'})

            updated_count = 0
            for item in updates:
                anomaly_id = item.get('anomaly_id')
                if not anomaly_id:
                    continue

                update_fields = []
                update_values = []

                if 'cause' in item:
                    update_fields.append('cause = %s')
                    update_values.append(item['cause'])

                if 'memo' in item:
                    update_fields.append('memo = %s')
                    update_values.append(item['memo'])

                if 'screenshot_id' in item:
                    update_fields.append('screenshot_id = %s')
                    update_values.append(item['screenshot_id'])

                if update_fields:
                    update_fields.append('updated_at = %s')
                    update_values.append(now)
                    update_fields.append('updated_id = %s')
                    update_values.append(user_id)
                    update_values.append(anomaly_id)

                    query = f"""
                        UPDATE ssd_crawl_db.ds_monitoring_report_anomaly
                        SET {', '.join(update_fields)}
                        WHERE id = %s AND is_del = 0
                    """
                    cursor.execute(query, update_values)
                    updated_count += cursor.rowcount

            conn.commit()
            cursor.close()
            conn.close()

            return JsonResponse({
                'success': True,
                'message': f'{updated_count}건 저장 완료',
                'updated_count': updated_count
            })

        # 단건 처리
        anomaly_id = body.get('anomaly_id')
        if not anomaly_id:
            return JsonResponse({'success': False, 'error': 'anomaly_id가 필요합니다.'})

        # 업데이트할 필드들 수집
        update_fields = []
        update_values = []

        if 'cause' in body:
            update_fields.append('cause = %s')
            update_values.append(body['cause'])

        if 'memo' in body:
            update_fields.append('memo = %s')
            update_values.append(body['memo'])

        if 'screenshot_id' in body:
            update_fields.append('screenshot_id = %s')
            update_values.append(body['screenshot_id'])

        if not update_fields:
            return JsonResponse({'success': False, 'error': '수정할 필드가 없습니다.'})

        update_fields.append('updated_at = %s')
        update_values.append(now)
        update_fields.append('updated_id = %s')
        update_values.append(user_id)
        update_values.append(anomaly_id)

        query = f"""
            UPDATE ssd_crawl_db.ds_monitoring_report_anomaly
            SET {', '.join(update_fields)}
            WHERE id = %s AND is_del = 0
        """
        cursor.execute(query, update_values)
        updated = cursor.rowcount

        conn.commit()
        cursor.close()
        conn.close()

        if updated == 0:
            return JsonResponse({'success': False, 'error': '해당 데이터를 찾을 수 없습니다.'})

        return JsonResponse({
            'success': True,
            'message': '수정 완료',
            'anomaly_id': anomaly_id
        })

    except Exception as e:
        log_error('report_update', e)
        return JsonResponse({'success': False, 'error': str(e)})


@csrf_exempt
@require_http_methods(["POST"])
def report_daily_update(request):
    """
    일별 보고서 메모 수정 API (단건 또는 일괄)

    POST 파라미터:
    - daily_id: report_daily ID (단건)
    - memo: 메모 (단건)
    또는
    - memos: [{daily_id, memo}, ...] (일괄)
    """
    try:
        body = json.loads(request.body)
        user_id = body.get('user_id', 'system')

        conn = get_ds_connection()
        cursor = conn.cursor()
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # 일괄 처리
        if 'memos' in body:
            memos = body['memos']
            if not memos or not isinstance(memos, list):
                return JsonResponse({'success': False, 'error': 'memos 배열이 필요합니다.'})

            updated_count = 0
            for item in memos:
                daily_id = item.get('daily_id')
                memo = item.get('memo', '')
                if daily_id:
                    cursor.execute("""
                        UPDATE ssd_crawl_db.ds_monitoring_report_daily
                        SET memo = %s, updated_at = %s, updated_id = %s
                        WHERE id = %s AND is_del = 0 AND is_closed = 0
                    """, (memo, now, user_id, daily_id))
                    updated_count += cursor.rowcount

            conn.commit()
            cursor.close()
            conn.close()

            return JsonResponse({
                'success': True,
                'message': f'{updated_count}건 메모 저장 완료',
                'updated_count': updated_count
            })

        # 단건 처리
        daily_id = body.get('daily_id')
        if not daily_id:
            return JsonResponse({'success': False, 'error': 'daily_id가 필요합니다.'})

        if 'memo' not in body:
            return JsonResponse({'success': False, 'error': 'memo 필드가 필요합니다.'})

        cursor.execute("""
            UPDATE ssd_crawl_db.ds_monitoring_report_daily
            SET memo = %s, updated_at = %s, updated_id = %s
            WHERE id = %s AND is_del = 0
        """, (body['memo'], now, user_id, daily_id))
        updated = cursor.rowcount

        conn.commit()
        cursor.close()
        conn.close()

        if updated == 0:
            return JsonResponse({'success': False, 'error': '해당 데이터를 찾을 수 없습니다.'})

        return JsonResponse({
            'success': True,
            'message': '메모 수정 완료',
            'daily_id': daily_id
        })

    except Exception as e:
        log_error('report_daily_update', e)
        return JsonResponse({'success': False, 'error': str(e)})


@csrf_exempt
@require_http_methods(["POST"])
def report_save_all(request):
    """
    미저장 리테일러 일괄 현황 저장 API (파일 정보 제외)

    POST 파라미터:
    - crawl_date: 수집일자 (YYYY-MM-DD)
    """
    try:
        body = json.loads(request.body)
        crawl_date = body.get('crawl_date')
        user_id = body.get('user_id', 'system')

        if not crawl_date:
            return JsonResponse({'success': False, 'error': 'crawl_date가 필요합니다.'})

        conn = get_ds_connection()
        cursor = conn.cursor()

        # 이미 마감되었는지 확인
        cursor.execute("""
            SELECT COUNT(*) FROM ssd_crawl_db.ds_monitoring_report_daily
            WHERE crawl_date = %s AND is_closed = 1 AND is_del = 0
        """, (crawl_date,))
        already_closed = cursor.fetchone()[0]

        if already_closed > 0:
            cursor.close()
            conn.close()
            return JsonResponse({'success': False, 'error': '이미 마감된 날짜입니다.'})

        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # 1. 이미 저장된 리테일러 목록 조회
        cursor.execute("""
            SELECT retailer FROM ssd_crawl_db.ds_monitoring_report_daily
            WHERE crawl_date = %s AND is_del = 0
        """, (crawl_date,))
        saved_retailers = set(row[0] for row in cursor.fetchall())

        # 2. 전체 모니터링 대상 리테일러 목록
        all_targets = get_monitoring_targets()
        all_retailers = set(target[1] for target in all_targets)

        # 3. 미저장 리테일러 자동 저장 (파일 정보 제외)
        unsaved_retailers = all_retailers - saved_retailers
        auto_saved_count = 0
        target_date = datetime.strptime(crawl_date, '%Y-%m-%d').date()

        for retailer in unsaved_retailers:
            stats = get_retailer_stats(cursor, retailer, target_date, include_file_info=False)
            if not stats:
                continue

            cursor.execute("""
                INSERT INTO ssd_crawl_db.ds_monitoring_report_daily (
                    crawl_date, retailer, expected_count, final_batch_count, total_count,
                    completion_rate, rerun_count, file_name, file_size,
                    anomaly_total, anomaly_title_null, anomaly_image_null,
                    anomaly_partial_null, anomaly_price_zero,
                    memo, is_closed, is_del, created_at, created_id
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, '', 0, %s, %s, %s, %s, %s, '', 0, 0, %s, %s
                )
            """, (
                crawl_date, retailer,
                stats['expected_count'],
                stats['final_batch_count'],
                stats['total_count'],
                stats['completion_rate'],
                stats['rerun_count'],
                stats['anomaly_total'],
                stats['anomaly_title_null'],
                stats['anomaly_image_null'],
                stats['anomaly_partial_null'],
                stats['anomaly_price_zero'],
                now, user_id
            ))
            auto_saved_count += 1

        conn.commit()
        cursor.close()
        conn.close()

        return JsonResponse({
            'success': True,
            'message': f'{crawl_date} 일괄 현황 저장 완료',
            'saved_count': auto_saved_count,
            'total_retailers': len(all_retailers),
            'already_saved': len(saved_retailers)
        })

    except Exception as e:
        log_error('report_save_all', e)
        return JsonResponse({'success': False, 'error': str(e)})


@csrf_exempt
@require_http_methods(["POST"])
def report_save_file_info(request):
    """
    파일서버에서 파일 정보 조회 후 전체 리테일러 file_name, file_size 업데이트

    POST 파라미터:
    - crawl_date: 수집일자 (YYYY-MM-DD)
    """
    try:
        body = json.loads(request.body)
        crawl_date = body.get('crawl_date')
        user_id = body.get('user_id', 'system')

        if not crawl_date:
            return JsonResponse({'success': False, 'error': 'crawl_date가 필요합니다.'})

        conn = get_ds_connection()
        cursor = conn.cursor()

        # 이미 마감되었는지 확인
        cursor.execute("""
            SELECT COUNT(*) FROM ssd_crawl_db.ds_monitoring_report_daily
            WHERE crawl_date = %s AND is_closed = 1 AND is_del = 0
        """, (crawl_date,))
        already_closed = cursor.fetchone()[0]

        if already_closed > 0:
            cursor.close()
            conn.close()
            return JsonResponse({'success': False, 'error': '이미 마감된 날짜입니다.'})

        # 전체 모니터링 대상 리테일러 수
        all_targets = get_monitoring_targets()
        all_retailers_count = len(all_targets)

        # 현황 테이블에 저장된 리테일러 수
        cursor.execute("""
            SELECT COUNT(*) FROM ssd_crawl_db.ds_monitoring_report_daily
            WHERE crawl_date = %s AND is_del = 0
        """, (crawl_date,))
        saved_count = cursor.fetchone()[0]

        # 모든 리테일러가 저장되어 있어야 파일 정보 저장 가능
        if saved_count < all_retailers_count:
            cursor.close()
            conn.close()
            return JsonResponse({
                'success': False,
                'error': f'일괄 현황 저장이 먼저 필요합니다. (저장: {saved_count}/{all_retailers_count})'
            })

        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        target_date = datetime.strptime(crawl_date, '%Y-%m-%d').date()

        # 파일서버에서 파일 정보 조회
        file_info_cache = get_file_info_for_date(target_date)

        # 각 리테일러별로 파일 정보 업데이트
        updated_count = 0
        for target in all_targets:
            retailer = target[1]
            retailer_file = file_info_cache.get(retailer, {})
            file_name = retailer_file.get('file_name', '')
            file_size = retailer_file.get('file_size', 0)

            cursor.execute("""
                UPDATE ssd_crawl_db.ds_monitoring_report_daily
                SET file_name = %s, file_size = %s, updated_at = %s, updated_id = %s
                WHERE crawl_date = %s AND retailer = %s AND is_del = 0
            """, (file_name, file_size, now, user_id, crawl_date, retailer))
            updated_count += cursor.rowcount

        conn.commit()
        cursor.close()
        conn.close()

        return JsonResponse({
            'success': True,
            'message': f'{crawl_date} 파일 정보 저장 완료',
            'updated_count': updated_count,
            'file_info_count': len(file_info_cache)
        })

    except Exception as e:
        log_error('report_save_file_info', e)
        return JsonResponse({'success': False, 'error': str(e)})


@csrf_exempt
@require_http_methods(["POST"])
def report_close(request):
    """
    일별 최종 마감 API (한 번만 가능)
    - 모든 리테일러가 현황 테이블에 저장되어 있어야 마감 가능
    - 마감 처리만 수행 (is_closed = 1)

    POST 파라미터:
    - crawl_date: 수집일자 (YYYY-MM-DD)
    """
    try:
        body = json.loads(request.body)
        crawl_date = body.get('crawl_date')
        user_id = body.get('user_id', 'system')

        if not crawl_date:
            return JsonResponse({'success': False, 'error': 'crawl_date가 필요합니다.'})

        conn = get_ds_connection()
        cursor = conn.cursor()

        # 이미 마감되었는지 확인
        cursor.execute("""
            SELECT COUNT(*) FROM ssd_crawl_db.ds_monitoring_report_daily
            WHERE crawl_date = %s AND is_closed = 1 AND is_del = 0
        """, (crawl_date,))
        already_closed = cursor.fetchone()[0]

        if already_closed > 0:
            cursor.close()
            conn.close()
            return JsonResponse({'success': False, 'error': '이미 마감된 날짜입니다.'})

        # 전체 모니터링 대상 리테일러 수
        all_targets = get_monitoring_targets()
        all_retailers_count = len(all_targets)

        # 현황 테이블에 저장된 리테일러 수
        cursor.execute("""
            SELECT COUNT(*) FROM ssd_crawl_db.ds_monitoring_report_daily
            WHERE crawl_date = %s AND is_del = 0
        """, (crawl_date,))
        saved_count = cursor.fetchone()[0]

        # 모든 리테일러가 저장되어 있어야 마감 가능
        if saved_count < all_retailers_count:
            cursor.close()
            conn.close()
            return JsonResponse({
                'success': False,
                'error': f'일괄 현황 저장이 먼저 필요합니다. (저장: {saved_count}/{all_retailers_count})'
            })

        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # 모든 리테일러 마감 처리
        cursor.execute("""
            UPDATE ssd_crawl_db.ds_monitoring_report_daily
            SET is_closed = 1, closed_at = %s, closed_id = %s, updated_at = %s, updated_id = %s
            WHERE crawl_date = %s AND is_del = 0
        """, (now, user_id, now, user_id, crawl_date))
        closed_count = cursor.rowcount

        conn.commit()
        cursor.close()
        conn.close()

        return JsonResponse({
            'success': True,
            'message': f'{crawl_date} 마감 완료',
            'closed_count': closed_count
        })

    except Exception as e:
        log_error('report_close', e)
        return JsonResponse({'success': False, 'error': str(e)})


def report_status(request):
    """
    날짜별 저장/마감 현황 조회 API

    GET 파라미터:
    - date: 수집일자 (YYYY-MM-DD)
    """
    date_str = request.GET.get('date')

    if date_str:
        target_date = date_str
    else:
        target_date = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')

    try:
        conn = get_ds_connection()
        cursor = conn.cursor()

        # 날짜별 마감 여부 확인
        cursor.execute("""
            SELECT is_closed FROM ssd_crawl_db.ds_monitoring_report_daily
            WHERE crawl_date = %s AND is_del = 0
            LIMIT 1
        """, (target_date,))
        row = cursor.fetchone()
        is_closed = row[0] == 1 if row else False

        # 리테일러별 저장 현황
        cursor.execute("""
            SELECT retailer, anomaly_total, anomaly_title_null, anomaly_image_null,
                   anomaly_partial_null, anomaly_price_zero, created_at, created_id
            FROM ssd_crawl_db.ds_monitoring_report_daily
            WHERE crawl_date = %s AND is_del = 0
        """, (target_date,))
        rows = cursor.fetchall()

        saved_retailers = {}
        for row in rows:
            saved_retailers[row[0]] = {
                'retailer': row[0],
                'anomaly_total': row[1],
                'anomaly_title_null': row[2],
                'anomaly_image_null': row[3],
                'anomaly_partial_null': row[4],
                'anomaly_price_zero': row[5],
                'created_at': row[6].strftime('%Y-%m-%d %H:%M:%S') if row[6] else None,
                'created_id': row[7]
            }

        cursor.close()
        conn.close()

        return JsonResponse({
            'success': True,
            'date': target_date,
            'is_closed': is_closed,
            'saved_retailers': saved_retailers
        })

    except Exception as e:
        log_error('report_status', e)
        return JsonResponse({'success': False, 'error': str(e)})


def report_list(request):
    """
    저장된 이상치 목록 조회 API (보고서 관리용)

    GET 파라미터:
    - date: 수집일자 (YYYY-MM-DD)
    - retailer: 리테일러명 (선택, 없으면 전체)
    """
    date_str = request.GET.get('date')
    retailer_filter = request.GET.get('retailer')

    if date_str:
        target_date = date_str
    else:
        target_date = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')

    try:
        conn = get_ds_connection()
        cursor = conn.cursor()

        # 날짜별 마감 여부 및 마감 정보 확인
        cursor.execute("""
            SELECT is_closed, closed_at, closed_id FROM ssd_crawl_db.ds_monitoring_report_daily
            WHERE crawl_date = %s AND is_del = 0
            LIMIT 1
        """, (target_date,))
        row = cursor.fetchone()
        is_closed = row[0] == 1 if row else False
        closed_at = row[1].strftime('%Y-%m-%d %H:%M:%S') if row and row[1] else None
        closed_id = row[2] if row else None

        # 리테일러별 일일 보고서 목록 조회
        daily_query = """
            SELECT id, retailer, expected_count, final_batch_count, total_count,
                   completion_rate, rerun_count, anomaly_total, anomaly_title_null,
                   anomaly_image_null, anomaly_partial_null, anomaly_price_zero,
                   memo, is_closed, created_at, created_id
            FROM ssd_crawl_db.ds_monitoring_report_daily
            WHERE crawl_date = %s AND is_del = 0
        """
        params = [target_date]
        if retailer_filter:
            daily_query += " AND retailer = %s"
            params.append(retailer_filter)
        daily_query += " ORDER BY retailer"

        cursor.execute(daily_query, params)
        daily_rows = cursor.fetchall()

        daily_reports = []
        for row in daily_rows:
            daily_reports.append({
                'id': row[0],
                'retailer': row[1],
                'expected_count': row[2],
                'final_batch_count': row[3],
                'total_count': row[4],
                'completion_rate': float(row[5]) if row[5] else 0,
                'rerun_count': row[6],
                'anomaly_total': row[7],
                'anomaly_title_null': row[8],
                'anomaly_image_null': row[9],
                'anomaly_partial_null': row[10],
                'anomaly_price_zero': row[11],
                'memo': row[12] or '',
                'is_closed': row[13] == 1,
                'created_at': row[14].strftime('%Y-%m-%d %H:%M:%S') if row[14] else None,
                'created_id': row[15]
            })

        # 이상치 목록 조회
        anomaly_query = """
            SELECT id, retailer, country_code, title, retailprice, ships_from, sold_by,
                   imageurl, producturl, screenshot_id, cause, memo, created_at, created_id,
                   updated_at, updated_id
            FROM ssd_crawl_db.ds_monitoring_report_anomaly
            WHERE crawl_date = %s AND is_del = 0
        """
        params = [target_date]
        if retailer_filter:
            anomaly_query += " AND retailer = %s"
            params.append(retailer_filter)
        anomaly_query += " ORDER BY retailer, id"

        cursor.execute(anomaly_query, params)
        anomaly_rows = cursor.fetchall()

        anomalies = []
        for row in anomaly_rows:
            anomalies.append({
                'id': row[0],
                'retailer': row[1],
                'country_code': row[2],
                'title': row[3],
                'retailprice': row[4],
                'ships_from': row[5],
                'sold_by': row[6],
                'imageurl': row[7],
                'producturl': row[8],
                'screenshot_id': row[9],
                'cause': row[10],
                'memo': row[11],
                'created_at': row[12].strftime('%Y-%m-%d %H:%M:%S') if row[12] else None,
                'created_id': row[13],
                'updated_at': row[14].strftime('%Y-%m-%d %H:%M:%S') if row[14] else None,
                'updated_id': row[15]
            })

        cursor.close()
        conn.close()

        # 전체 모니터링 대상 리테일러 수
        all_targets = get_monitoring_targets()
        total_retailers = len(all_targets)

        return JsonResponse({
            'success': True,
            'date': target_date,
            'is_closed': is_closed,
            'closed_at': closed_at,
            'closed_id': closed_id,
            'daily_reports': daily_reports,
            'anomalies': anomalies,
            'total_anomalies': len(anomalies),
            'total_retailers': total_retailers
        })

    except Exception as e:
        log_error('report_list', e)
        return JsonResponse({'success': False, 'error': str(e)})
