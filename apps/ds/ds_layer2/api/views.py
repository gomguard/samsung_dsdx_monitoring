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
import paramiko
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from datetime import datetime, timedelta, date
from apps.common.db import get_ds_connection
from apps.common.targets import load_monitoring_targets, load_monitoring_targets_with_instance, format_time
from apps.common.response import safe_error, log_error
from config.config import FILE_SERVER_CONFIG, S3_CONFIG, SSM_CONFIG
import boto3
from botocore.exceptions import ClientError


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
        log_error(e)

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
        log_error(e)
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
        results['error'] = log_error(e)

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
        results['error'] = log_error(e)

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
                    SELECT t.retailer, r.expected_count, r.total_count,
                           r.anomaly_total, r.anomaly_title_null, r.anomaly_image_null,
                           r.anomaly_partial_null, r.anomaly_price_zero,
                           r.final_batch_count
                    FROM ssd_crawl_db.ds_monitoring_report_daily r
                    JOIN ssd_crawl_db.ds_monitoring_targets t ON r.retailer_id = t.retailer_id
                    WHERE r.crawl_date = %s AND r.is_del = 0
                """, (target_date,))
                for row in cursor.fetchall():
                    anomaly_total = row[3] or 0
                    a_title_null = row[4] or 0  # 실제로는 null_union
                    a_image_null = row[5] or 0
                    a_partial_null = row[6] or 0
                    a_price_zero = row[7] or 0
                    a_imageurl_invalid = max(0, anomaly_total - a_title_null - a_price_zero - a_partial_null)
                    snap_total = row[2] or 0
                    snap_final = row[8] or 0
                    closed_data[row[0]] = {
                        'expected_count': row[1] or 0,
                        'total': snap_total,
                        'final_batch_count': snap_final,
                        'title_null': a_title_null,
                        'imageurl_null': a_image_null,
                        'null_union': a_title_null,
                        'imageurl_invalid': a_imageurl_invalid,
                        'price_zero': a_price_zero,
                        'partial_null': a_partial_null,
                        'all_null': 0,
                        'valid': max(0, snap_total - anomaly_total),
                        'valid_final': max(0, snap_final - anomaly_total),
                        'error_count': anomaly_total,
                    }
        except:
            is_closed = False

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

        for idx, (table_name, retailer, region, korea_time, country, mall_name, instance_id, schedule_name) in enumerate(load_monitoring_targets_with_instance(), 1):
            retailer_batches = batches_by_retailer.get(retailer, [])

            # 마감된 날짜 + 현황 데이터 있음 → 스냅샷 사용 (실시간 쿼리 생략)
            if is_closed and retailer in closed_data:
                snap = closed_data[retailer]
                # batch_view에 따라 전체/최종 배치 건수 선택
                if batch_view == 'final' and snap['final_batch_count'] != snap['total']:
                    total = snap['final_batch_count']
                    valid = snap['valid_final']
                else:
                    total = snap['total']
                    valid = snap['valid']
                expected_count = snap['expected_count']
                title_null = snap['title_null']
                imageurl_null = snap['imageurl_null']
                null_union = snap['null_union']
                imageurl_invalid = snap['imageurl_invalid']
                price_zero = snap['price_zero']
                partial_null = snap['partial_null']
                all_null = snap['all_null']
                error_count = snap['error_count']

                # 상태 판정
                if total == 0:
                    status = 'pending'
                elif error_count == 0:
                    status = 'success'
                elif error_count < total * 0.05:
                    status = 'warning'
                else:
                    status = 'danger'

                total_records += total
                total_title_null += title_null
                total_imageurl_null += imageurl_null
                total_null_union += null_union
                total_imageurl_invalid += imageurl_invalid
                total_price_zero += price_zero
                total_partial_null += partial_null
                total_all_null += all_null
                total_valid += valid

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
                    'batch_count': 0,
                    'has_multi_batch': False,
                    'batches': [],
                    'final_start_time': None,
                    'final_end_time': None,
                    'has_screenshot': bool(instance_id)
                })
                continue

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
                'final_end_time': final_end_time,
                'has_screenshot': bool(instance_id)  # instance_id가 있으면 스크린샷 지원
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
            'status': overall_status,
            'is_closed': is_closed
        }

    except Exception as e:
        data['error'] = log_error(e)
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
    try:
        page = max(1, int(request.GET.get('page', 1)))
        page_size = min(int(request.GET.get('page_size', 50)), 200)
    except (ValueError, TypeError):
        return JsonResponse({'error': '잘못된 페이지 파라미터'}, status=400)

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
            SELECT title, retailprice, ships_from, sold_by, imageurl, producturl, retailersku, crawl_strdatetime
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
            crawl_dt = row[7] or ''
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
                'retailersku': row[6] or '',
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
        data['error'] = log_error(e)

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
        log_error(e)

    return file_info


def get_retailer_stats(cursor, retailer, target_date, file_info_cache=None, include_file_info=True):
    """
    리테일러의 통계 데이터 계산 (공통 함수)
    - retailer_id: 리테일러 ID
    - expected_count: 예상 수집 건수
    - total_count: 하루 전체 수집 건수
    - final_batch_count: 최종 배치 건수
    - completion_rate: 완료율
    - rerun_count: 재실행 횟수
    - 이상치 통계 (최종 배치 기준)
    - file_name, file_size: include_file_info=True일 때만 file_info_cache에서 조회
    """
    # 리테일러 타겟 정보 찾기 (retailer_id 포함)
    cursor.execute("""
        SELECT retailer_id, table_name, country, mall_name
        FROM ssd_crawl_db.ds_monitoring_targets
        WHERE retailer = %s AND is_active = 1
    """, (retailer,))
    target_row = cursor.fetchone()

    if not target_row:
        return None

    retailer_id = target_row[0]
    table_name = target_row[1]
    country = target_row[2]
    mall_name = target_row[3]

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
        'retailer_id': retailer_id,
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

        retailer_id = stats['retailer_id']

        # 1. 기존 활성 데이터 soft delete (is_del = 1)
        cursor.execute("""
            UPDATE ssd_crawl_db.ds_monitoring_report_daily
            SET is_del = 1, updated_at = %s, updated_id = %s
            WHERE crawl_date = %s AND retailer_id = %s AND is_del = 0
        """, (now, user_id, crawl_date, retailer_id))

        cursor.execute("""
            UPDATE ssd_crawl_db.ds_monitoring_report_anomaly
            SET is_del = 1, updated_at = %s, updated_id = %s
            WHERE crawl_date = %s AND retailer_id = %s AND is_del = 0
        """, (now, user_id, crawl_date, retailer_id))

        # 2. report_daily — 기존 soft-deleted 레코드 복구 또는 신규 INSERT
        cursor.execute("""
            SELECT id FROM ssd_crawl_db.ds_monitoring_report_daily
            WHERE crawl_date = %s AND retailer_id = %s AND is_del = 1
            ORDER BY updated_at DESC LIMIT 1
        """, (crawl_date, retailer_id))
        old_daily = cursor.fetchone()

        if old_daily:
            # 기존 레코드 복구: 통계만 갱신, file_name/file_size는 유지
            report_daily_id = old_daily[0]
            cursor.execute("""
                UPDATE ssd_crawl_db.ds_monitoring_report_daily
                SET is_del = 0,
                    expected_count = %s, final_batch_count = %s, total_count = %s,
                    completion_rate = %s, rerun_count = %s,
                    anomaly_total = %s, anomaly_title_null = %s, anomaly_image_null = %s,
                    anomaly_partial_null = %s, anomaly_price_zero = %s,
                    memo = %s, updated_at = %s, updated_id = %s
                WHERE id = %s
            """, (
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
                now, user_id,
                report_daily_id
            ))
        else:
            # 최초 저장: 신규 INSERT (파일 정보는 별도 API에서 저장)
            cursor.execute("""
                INSERT INTO ssd_crawl_db.ds_monitoring_report_daily (
                    crawl_date, retailer_id, expected_count, final_batch_count, total_count,
                    completion_rate, rerun_count, file_name, file_size,
                    anomaly_total, anomaly_title_null, anomaly_image_null,
                    anomaly_partial_null, anomaly_price_zero,
                    memo, is_del, created_at, created_id
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, '', 0, %s, %s, %s, %s, %s, %s, 0, %s, %s
                )
            """, (
                crawl_date, retailer_id,
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

        # 3. report_anomaly — retailersku 매칭으로 복구 또는 신규 INSERT
        #    복구 시 screenshot_id, cause, memo 유지
        cursor.execute("""
            SELECT id, retailersku, screenshot_id, cause, memo
            FROM ssd_crawl_db.ds_monitoring_report_anomaly
            WHERE crawl_date = %s AND retailer_id = %s AND is_del = 1
        """, (crawl_date, retailer_id))
        old_anomaly_rows = cursor.fetchall()

        # retailersku → {id, screenshot_id, cause, memo} 매핑 (첫 매칭만 사용)
        old_anomaly_map = {}
        for row in old_anomaly_rows:
            sku = row[1]
            if sku and sku not in old_anomaly_map:
                old_anomaly_map[sku] = {
                    'id': row[0],
                    'screenshot_id': row[2],
                    'cause': row[3],
                    'memo': row[4]
                }

        anomaly_ids = []
        for anomaly in anomalies:
            sku = anomaly.get('retailersku', '')
            old = old_anomaly_map.pop(sku, None) if sku else None

            if old:
                # 기존 레코드 복구: 상품 데이터 갱신, screenshot_id/cause/memo 유지
                cursor.execute("""
                    UPDATE ssd_crawl_db.ds_monitoring_report_anomaly
                    SET is_del = 0,
                        country_code = %s, title = %s, retailprice = %s,
                        ships_from = %s, sold_by = %s, imageurl = %s, producturl = %s,
                        updated_at = %s, updated_id = %s
                    WHERE id = %s
                """, (
                    anomaly.get('country_code', ''),
                    anomaly.get('title', ''),
                    anomaly.get('retailprice'),
                    anomaly.get('ships_from', ''),
                    anomaly.get('sold_by', ''),
                    anomaly.get('imageurl', ''),
                    anomaly.get('producturl', ''),
                    now, user_id,
                    old['id']
                ))
                anomaly_ids.append(old['id'])
            else:
                # 신규 INSERT (매칭 안 되는 이상치)
                cursor.execute("""
                    INSERT INTO ssd_crawl_db.ds_monitoring_report_anomaly (
                        crawl_date, retailer_id, country_code, title, retailprice,
                        ships_from, sold_by, imageurl, producturl, retailersku,
                        screenshot_id, cause, memo, is_del, created_at, created_id
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 0, %s, %s
                    )
                """, (
                    crawl_date, retailer_id,
                    anomaly.get('country_code', ''),
                    anomaly.get('title', ''),
                    anomaly.get('retailprice'),
                    anomaly.get('ships_from', ''),
                    anomaly.get('sold_by', ''),
                    anomaly.get('imageurl', ''),
                    anomaly.get('producturl', ''),
                    anomaly.get('retailersku', ''),
                    anomaly.get('screenshot_id'),
                    anomaly.get('cause', ''),
                    anomaly.get('memo', ''),
                    now, user_id
                ))
                anomaly_ids.append(cursor.lastrowid)

        # 4. 미매칭 이상치의 스크린샷 파일 soft delete
        orphan_screenshot_ids = [
            v['screenshot_id'] for v in old_anomaly_map.values()
            if v['screenshot_id']
        ]
        if orphan_screenshot_ids:
            placeholders = ','.join(['%s'] * len(orphan_screenshot_ids))
            cursor.execute(f"""
                UPDATE ssd_crawl_db.ds_monitoring_file
                SET is_del = 1, updated_at = %s
                WHERE file_id IN ({placeholders}) AND is_del = 0
            """, [now] + orphan_screenshot_ids)

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
        return safe_error(e, success=False)


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

        # retailer_id 조회
        cursor.execute("""
            SELECT retailer_id FROM ssd_crawl_db.ds_monitoring_targets
            WHERE retailer = %s AND is_active = 1
        """, (retailer,))
        row = cursor.fetchone()
        if not row:
            cursor.close()
            conn.close()
            return JsonResponse({'success': False, 'error': f'{retailer} 타겟 정보를 찾을 수 없습니다.'})
        retailer_id = row[0]

        # report_daily soft delete
        cursor.execute("""
            UPDATE ssd_crawl_db.ds_monitoring_report_daily
            SET is_del = 1, updated_at = %s, updated_id = %s
            WHERE crawl_date = %s AND retailer_id = %s AND is_del = 0
        """, (now, user_id, crawl_date, retailer_id))
        daily_deleted = cursor.rowcount

        # report_anomaly soft delete
        cursor.execute("""
            UPDATE ssd_crawl_db.ds_monitoring_report_anomaly
            SET is_del = 1, updated_at = %s, updated_id = %s
            WHERE crawl_date = %s AND retailer_id = %s AND is_del = 0
        """, (now, user_id, crawl_date, retailer_id))
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
        return safe_error(e, success=False)


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
        return safe_error(e, success=False)


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
                        WHERE id = %s AND is_del = 0
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
        return safe_error(e, success=False)


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

        # 이미 마감되었는지 확인 (report_close 테이블)
        cursor.execute("""
            SELECT is_closed FROM ssd_crawl_db.ds_monitoring_report_close
            WHERE crawl_date = %s
        """, (crawl_date,))
        close_row = cursor.fetchone()

        if close_row and close_row[0] == 1:
            cursor.close()
            conn.close()
            return JsonResponse({'success': False, 'error': '이미 마감된 날짜입니다.'})

        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # 1. 이미 저장된 retailer_id 목록 조회
        cursor.execute("""
            SELECT retailer_id FROM ssd_crawl_db.ds_monitoring_report_daily
            WHERE crawl_date = %s AND is_del = 0
        """, (crawl_date,))
        saved_retailer_ids = set(row[0] for row in cursor.fetchall())

        # 2. 전체 모니터링 대상 리테일러 목록 (retailer_id, retailer 포함)
        cursor.execute("""
            SELECT retailer_id, retailer FROM ssd_crawl_db.ds_monitoring_targets
            WHERE is_active = 1
        """)
        all_targets_map = {row[0]: row[1] for row in cursor.fetchall()}
        all_retailer_ids = set(all_targets_map.keys())

        # 3. 미저장 리테일러 자동 저장 (파일 정보 제외)
        unsaved_retailer_ids = all_retailer_ids - saved_retailer_ids
        auto_saved_count = 0
        target_date = datetime.strptime(crawl_date, '%Y-%m-%d').date()

        for retailer_id in unsaved_retailer_ids:
            retailer = all_targets_map[retailer_id]
            stats = get_retailer_stats(cursor, retailer, target_date, include_file_info=False)
            if not stats:
                continue

            cursor.execute("""
                INSERT INTO ssd_crawl_db.ds_monitoring_report_daily (
                    crawl_date, retailer_id, expected_count, final_batch_count, total_count,
                    completion_rate, rerun_count, file_name, file_size,
                    anomaly_total, anomaly_title_null, anomaly_image_null,
                    anomaly_partial_null, anomaly_price_zero,
                    memo, is_del, created_at, created_id
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, '', 0, %s, %s, %s, %s, %s, '', 0, %s, %s
                )
            """, (
                crawl_date, retailer_id,
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
            'total_retailers': len(all_retailer_ids),
            'already_saved': len(saved_retailer_ids)
        })

    except Exception as e:
        return safe_error(e, success=False)


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

        # 이미 마감되었는지 확인 (report_close 테이블)
        cursor.execute("""
            SELECT is_closed FROM ssd_crawl_db.ds_monitoring_report_close
            WHERE crawl_date = %s
        """, (crawl_date,))
        close_row = cursor.fetchone()

        if close_row and close_row[0] == 1:
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

        # 전체 리테일러 목록 (retailer_id, retailer 포함)
        cursor.execute("""
            SELECT retailer_id, retailer FROM ssd_crawl_db.ds_monitoring_targets
            WHERE is_active = 1
        """)
        targets_list = cursor.fetchall()

        # 각 리테일러별로 파일 정보 업데이트
        updated_count = 0
        for target_row in targets_list:
            retailer_id = target_row[0]
            retailer = target_row[1]
            retailer_file = file_info_cache.get(retailer, {})
            file_name = retailer_file.get('file_name', '')
            file_size = retailer_file.get('file_size', 0)

            cursor.execute("""
                UPDATE ssd_crawl_db.ds_monitoring_report_daily
                SET file_name = %s, file_size = %s, updated_at = %s, updated_id = %s
                WHERE crawl_date = %s AND retailer_id = %s AND is_del = 0
            """, (file_name, file_size, now, user_id, crawl_date, retailer_id))
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
        return safe_error(e, success=False)


@require_http_methods(["POST"])
def report_close(request):
    """
    일별 최종 마감 API
    - 모든 리테일러가 현황 테이블에 저장되어 있어야 마감 가능
    - report_close 테이블에 마감 상태 저장
    - report_close_history 테이블에 이력 저장

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

        # 이미 마감되었는지 확인 (report_close 테이블)
        cursor.execute("""
            SELECT is_closed FROM ssd_crawl_db.ds_monitoring_report_close
            WHERE crawl_date = %s
        """, (crawl_date,))
        close_row = cursor.fetchone()

        if close_row and close_row[0] == 1:
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

        # 마감 상태 저장 (report_close 테이블)
        cursor.execute("""
            INSERT INTO ssd_crawl_db.ds_monitoring_report_close
                (crawl_date, is_closed, closed_at, closed_id, created_at, updated_at)
            VALUES (%s, 1, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                is_closed = 1, closed_at = %s, closed_id = %s, updated_at = %s
        """, (crawl_date, now, user_id, now, now, now, user_id, now))

        # 마감 이력 저장 (report_close_history 테이블)
        cursor.execute("""
            INSERT INTO ssd_crawl_db.ds_monitoring_report_close_history
                (crawl_date, action, action_at, action_id)
            VALUES (%s, 'close', %s, %s)
        """, (crawl_date, now, user_id))

        conn.commit()
        cursor.close()
        conn.close()

        return JsonResponse({
            'success': True,
            'message': f'{crawl_date} 마감 완료'
        })

    except Exception as e:
        return safe_error(e, success=False)


@require_http_methods(["POST"])
def report_cancel_close(request):
    """
    마감 취소 API
    - report_close 테이블의 is_closed = 0 으로 변경
    - report_close_history 테이블에 cancel 이력 저장

    POST 파라미터:
    - crawl_date: 수집일자 (YYYY-MM-DD)
    - memo: 취소 사유 (선택)
    """
    try:
        body = json.loads(request.body)
        crawl_date = body.get('crawl_date')
        user_id = body.get('user_id', 'system')
        memo = body.get('memo', '')

        if not crawl_date:
            return JsonResponse({'success': False, 'error': 'crawl_date가 필요합니다.'})

        conn = get_ds_connection()
        cursor = conn.cursor()

        # 마감 상태 확인
        cursor.execute("""
            SELECT is_closed FROM ssd_crawl_db.ds_monitoring_report_close
            WHERE crawl_date = %s
        """, (crawl_date,))
        close_row = cursor.fetchone()

        if not close_row or close_row[0] != 1:
            cursor.close()
            conn.close()
            return JsonResponse({'success': False, 'error': '마감되지 않은 날짜입니다.'})

        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # 마감 취소 (is_closed = 0)
        cursor.execute("""
            UPDATE ssd_crawl_db.ds_monitoring_report_close
            SET is_closed = 0, updated_at = %s
            WHERE crawl_date = %s
        """, (now, crawl_date))

        # 취소 이력 저장
        cursor.execute("""
            INSERT INTO ssd_crawl_db.ds_monitoring_report_close_history
                (crawl_date, action, action_at, action_id, memo)
            VALUES (%s, 'cancel', %s, %s, %s)
        """, (crawl_date, now, user_id, memo))

        conn.commit()
        cursor.close()
        conn.close()

        return JsonResponse({
            'success': True,
            'message': f'{crawl_date} 마감 취소 완료'
        })

    except Exception as e:
        return safe_error(e, success=False)


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

        # 날짜별 마감 여부 확인 (report_close 테이블)
        cursor.execute("""
            SELECT is_closed FROM ssd_crawl_db.ds_monitoring_report_close
            WHERE crawl_date = %s
        """, (target_date,))
        close_row = cursor.fetchone()
        is_closed = close_row[0] == 1 if close_row else False

        # 리테일러별 저장 현황
        cursor.execute("""
            SELECT t.retailer, d.anomaly_total, d.anomaly_title_null, d.anomaly_image_null,
                   d.anomaly_partial_null, d.anomaly_price_zero, d.created_at, d.created_id
            FROM ssd_crawl_db.ds_monitoring_report_daily d
            LEFT JOIN ssd_crawl_db.ds_monitoring_targets t ON d.retailer_id = t.retailer_id
            WHERE d.crawl_date = %s AND d.is_del = 0
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
        return safe_error(e, success=False)


def report_list(request):
    """
    저장된 이상치 목록 조회 API (보고서 관리용)

    GET 파라미터:
    - date: 수집일자 (YYYY-MM-DD)
    - retailer: 리테일러명 (선택, 없으면 전체)
    - view: 'status'(현황) | 'detail'(상세) - 기본 'status'
    """
    date_str = request.GET.get('date')
    retailer_filter = request.GET.get('retailer')
    view_mode = request.GET.get('view', 'status')

    if date_str:
        target_date = date_str
    else:
        target_date = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')

    try:
        conn = get_ds_connection()
        cursor = conn.cursor()

        # 날짜별 마감 여부 및 마감 정보 확인 (report_close 테이블)
        cursor.execute("""
            SELECT is_closed, closed_at, closed_id FROM ssd_crawl_db.ds_monitoring_report_close
            WHERE crawl_date = %s
        """, (target_date,))
        close_row = cursor.fetchone()
        is_closed = close_row[0] == 1 if close_row else False
        closed_at = close_row[1].strftime('%Y-%m-%d %H:%M:%S') if close_row and close_row[1] else None
        closed_id = close_row[2] if close_row else None

        # 리테일러별 일일 보고서 목록 조회 (ds_monitoring_targets.sort_order 순서)
        daily_query = """
            SELECT d.id, t.retailer, d.expected_count, d.final_batch_count, d.total_count,
                   d.completion_rate, d.rerun_count, d.anomaly_total, d.anomaly_title_null,
                   d.anomaly_image_null, d.anomaly_partial_null, d.anomaly_price_zero,
                   d.memo, d.created_at, d.created_id, d.file_name, d.file_size,
                   t.instance_id
            FROM ssd_crawl_db.ds_monitoring_report_daily d
            LEFT JOIN ssd_crawl_db.ds_monitoring_targets t ON d.retailer_id = t.retailer_id
            WHERE d.crawl_date = %s AND d.is_del = 0
        """
        params = [target_date]
        if retailer_filter:
            daily_query += " AND t.retailer = %s"
            params.append(retailer_filter)
        daily_query += " ORDER BY t.sort_order, t.retailer"

        cursor.execute(daily_query, params)
        daily_rows = cursor.fetchall()

        daily_reports = []
        for row in daily_rows:
            instance_id = row[17] if len(row) > 17 else None
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
                'created_at': row[13].strftime('%Y-%m-%d %H:%M:%S') if row[13] else None,
                'created_id': row[14],
                'file_name': row[15] or '',
                'file_size': row[16] or 0,
                'has_screenshot': bool(instance_id)
            })

        anomalies = []
        cause_options = {}

        if view_mode == 'detail':
            # 상세 모드: 이상치 전체 목록 조회
            anomaly_query = """
                SELECT a.id, t.retailer, a.country_code, a.title, a.retailprice, a.ships_from, a.sold_by,
                       a.imageurl, a.producturl, a.retailersku, a.screenshot_id, a.cause, a.memo, a.created_at, a.created_id,
                       a.updated_at, a.updated_id
                FROM ssd_crawl_db.ds_monitoring_report_anomaly a
                LEFT JOIN ssd_crawl_db.ds_monitoring_targets t ON a.retailer_id = t.retailer_id
                WHERE a.crawl_date = %s AND a.is_del = 0
            """
            params = [target_date]
            if retailer_filter:
                anomaly_query += " AND t.retailer = %s"
                params.append(retailer_filter)
            anomaly_query += " ORDER BY t.sort_order, t.retailer, a.id"

            cursor.execute(anomaly_query, params)
            anomaly_rows = cursor.fetchall()

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
                    'retailersku': row[9] or '',
                    'screenshot_id': row[10],
                    'cause': row[11],
                    'memo': row[12],
                    'created_at': row[13].strftime('%Y-%m-%d %H:%M:%S') if row[13] else None,
                    'created_id': row[14],
                    'updated_at': row[15].strftime('%Y-%m-%d %H:%M:%S') if row[15] else None,
                    'updated_id': row[16]
                })

            # 리테일러별 원인 옵션 조회
            cursor.execute("""
                SELECT t.retailer, o.option_name
                FROM ssd_crawl_db.ds_monitoring_anomaly_causes_options o
                JOIN ssd_crawl_db.ds_monitoring_targets t ON o.retailer_id = t.retailer_id
                WHERE o.is_active = 1
                ORDER BY t.retailer, o.sort_order, o.option_id
            """)
            cause_rows = cursor.fetchall()
            for row in cause_rows:
                retailer = row[0]
                option_name = row[1]
                if retailer not in cause_options:
                    cause_options[retailer] = []
                cause_options[retailer].append(option_name)

        # 리테일러별 원인 카운트 요약 조회 (현황 메모 자동입력용)
        cause_summary_query = """
            SELECT t.retailer,
                   COALESCE(a.cause, '') as cause,
                   COUNT(*) as cnt
            FROM ssd_crawl_db.ds_monitoring_report_anomaly a
            LEFT JOIN ssd_crawl_db.ds_monitoring_targets t ON a.retailer_id = t.retailer_id
            WHERE a.crawl_date = %s AND a.is_del = 0
            GROUP BY t.retailer, a.cause
            ORDER BY t.retailer, cnt DESC
        """
        cursor.execute(cause_summary_query, [target_date])
        cause_summary_rows = cursor.fetchall()
        cause_summary = {}
        for row in cause_summary_rows:
            retailer = row[0]
            cause = row[1] or '미입력'
            cnt = row[2]
            if retailer not in cause_summary:
                cause_summary[retailer] = {}
            cause_summary[retailer][cause] = cnt

        # 이상치 요약 카운트 조회 (현황/상세 공통)
        summary_query = """
            SELECT COUNT(*) as total,
                   SUM(CASE WHEN a.cause IS NOT NULL AND a.cause != '' THEN 1 ELSE 0 END) as filled_cause,
                   SUM(CASE WHEN a.memo IS NOT NULL AND a.memo != '' THEN 1 ELSE 0 END) as filled_memo
            FROM ssd_crawl_db.ds_monitoring_report_anomaly a
            WHERE a.crawl_date = %s AND a.is_del = 0
        """
        summary_params = [target_date]
        if retailer_filter:
            summary_query += """ AND a.retailer_id IN (
                SELECT t.retailer_id FROM ssd_crawl_db.ds_monitoring_targets t WHERE t.retailer = %s
            )"""
            summary_params.append(retailer_filter)
        cursor.execute(summary_query, summary_params)
        summary_row = cursor.fetchone()
        total_anomalies = summary_row[0] if summary_row else 0
        filled_cause = summary_row[1] if summary_row else 0
        filled_memo = summary_row[2] if summary_row else 0

        # 리테일러별 스크린샷 캡쳐 현황 조회
        screenshot_query = """
            SELECT t.retailer,
                   COUNT(*) as total,
                   SUM(CASE WHEN a.screenshot_id IS NOT NULL THEN 1 ELSE 0 END) as captured
            FROM ssd_crawl_db.ds_monitoring_report_anomaly a
            LEFT JOIN ssd_crawl_db.ds_monitoring_targets t ON a.retailer_id = t.retailer_id
            WHERE a.crawl_date = %s AND a.is_del = 0
            GROUP BY t.retailer
        """
        cursor.execute(screenshot_query, [target_date])
        screenshot_rows = cursor.fetchall()
        screenshot_status_by_retailer = {}
        total_screenshots = 0
        captured_screenshots = 0
        for row in screenshot_rows:
            screenshot_status_by_retailer[row[0]] = {'total': row[1], 'captured': row[2]}
            total_screenshots += row[1]
            captured_screenshots += row[2]

        # 캡쳐 로그: 30분 넘은 running → failed 자동 정리 (비정상 종료 안전장치)
        running_captures = {}
        try:
            cursor.execute("""
                UPDATE ssd_crawl_db.ds_monitoring_capture_log
                SET status = 'failed'
                WHERE crawl_date = %s AND status = 'running'
                AND triggered_at < %s
            """, (target_date, datetime.now() - timedelta(minutes=30)))
            if cursor.rowcount > 0:
                conn.commit()

            # 30분 이내 running 조회
            cursor.execute("""
                SELECT t.retailer, cl.triggered_at
                FROM ssd_crawl_db.ds_monitoring_capture_log cl
                JOIN ssd_crawl_db.ds_monitoring_targets t ON cl.retailer_id = t.retailer_id
                WHERE cl.crawl_date = %s AND cl.status = 'running'
                AND cl.triggered_at >= %s
            """, (target_date, datetime.now() - timedelta(minutes=30)))
            for row in cursor.fetchall():
                running_captures[row[0]] = row[1].strftime('%Y-%m-%d %H:%M:%S') if row[1] else None
        except:
            pass

        # daily_reports에 all_screenshots_captured + capture_running 필드 추가
        for report in daily_reports:
            retailer = report['retailer']
            status = screenshot_status_by_retailer.get(retailer, {'total': 0, 'captured': 0})
            report['all_screenshots_captured'] = status['total'] > 0 and status['total'] == status['captured']
            report['capture_running'] = retailer in running_captures

        cursor.close()
        conn.close()

        # 전체 모니터링 대상 리테일러 수
        all_targets = get_monitoring_targets()
        total_retailers = len(all_targets)

        return JsonResponse({
            'success': True,
            'date': target_date,
            'view': view_mode,
            'is_closed': is_closed,
            'closed_at': closed_at,
            'closed_id': closed_id,
            'daily_reports': daily_reports,
            'anomalies': anomalies,
            'total_anomalies': total_anomalies,
            'filled_cause': filled_cause,
            'filled_memo': filled_memo,
            'total_screenshots': total_screenshots,
            'captured_screenshots': captured_screenshots,
            'total_retailers': total_retailers,
            'cause_options': cause_options,
            'cause_summary': cause_summary
        })

    except Exception as e:
        return safe_error(e, success=False)


def get_screenshot_url(request):
    """
    스크린샷 이미지 URL 조회 API

    GET 파라미터:
    - file_id: ds_monitoring_file.file_id

    반환: S3 pre-signed URL (1시간 유효)
    """
    file_id = request.GET.get('file_id')

    if not file_id:
        return JsonResponse({'success': False, 'error': 'file_id is required'})

    try:
        conn = get_ds_connection()
        cursor = conn.cursor()

        # ds_monitoring_file에서 file_path 조회
        cursor.execute("""
            SELECT file_path, file_name, file_type
            FROM ssd_crawl_db.ds_monitoring_file
            WHERE file_id = %s AND is_del = 0
        """, (file_id,))
        row = cursor.fetchone()

        cursor.close()
        conn.close()

        if not row:
            return JsonResponse({'success': False, 'error': 'File not found'})

        file_path = row[0]  # 디렉토리 경로
        file_name = row[1]  # 파일명
        file_type = row[2]

        # S3 key: 경로 + 파일명
        s3_key = file_path.rstrip('/') + '/' + file_name

        # S3 pre-signed URL 생성
        s3_client = boto3.client(
            's3',
            region_name=S3_CONFIG['region'],
            aws_access_key_id=S3_CONFIG['access_key'],
            aws_secret_access_key=S3_CONFIG['secret_key']
        )

        url = s3_client.generate_presigned_url(
            'get_object',
            Params={
                'Bucket': S3_CONFIG['bucket'],
                'Key': s3_key
            },
            ExpiresIn=3600  # 1시간 유효
        )

        return JsonResponse({
            'success': True,
            'url': url,
            'file_name': file_name,
            'file_type': file_type
        })

    except ClientError as e:
        return safe_error(e, 's3', success=False)
    except Exception as e:
        return safe_error(e, success=False)


def screenshot_capture(request):
    """SSM을 통해 EC2 인스턴스에서 스크린샷 캡쳐 명령 실행 API"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST 요청만 허용됩니다.'}, status=405)

    try:
        body = json.loads(request.body)
    except:
        return JsonResponse({'error': '잘못된 요청 형식입니다.'}, status=400)

    retailer = body.get('retailer')
    crawl_date = body.get('crawl_date')

    if not retailer or not crawl_date:
        return JsonResponse({'error': '리테일러와 날짜가 필요합니다.'}, status=400)

    # DB에서 해당 리테일러의 instance_id, instance_region, retailer_id 조회
    conn = None
    cursor = None
    try:
        conn = get_ds_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT retailer_id, instance_id, instance_region, mall_name FROM ssd_crawl_db.ds_monitoring_targets
            WHERE retailer = %s AND is_active = 1
        """, (retailer,))
        row = cursor.fetchone()

        if not row:
            return JsonResponse({'error': '해당 리테일러를 찾을 수 없습니다.'}, status=404)

        retailer_id = row[0]
        instance_id = row[1]
        instance_region = row[2] or SSM_CONFIG['region']  # NULL이면 기본값 사용
        mall_name = row[3]

        if not instance_id:
            return JsonResponse({'error': '이 리테일러는 스크린샷 캡쳐를 지원하지 않습니다.'}, status=400)

        # 30분 넘은 running → failed 자동 정리 (비정상 종료 안전장치)
        cursor.execute("""
            UPDATE ssd_crawl_db.ds_monitoring_capture_log
            SET status = 'failed'
            WHERE retailer_id = %s AND crawl_date = %s AND status = 'running'
            AND triggered_at < %s
        """, (retailer_id, crawl_date, datetime.now() - timedelta(minutes=30)))
        if cursor.rowcount > 0:
            conn.commit()

        # running 기록 확인 (중복 실행 방지)
        cursor.execute("""
            SELECT id, triggered_at FROM ssd_crawl_db.ds_monitoring_capture_log
            WHERE retailer_id = %s AND crawl_date = %s AND status = 'running'
            ORDER BY triggered_at DESC LIMIT 1
        """, (retailer_id, crawl_date))
        running_row = cursor.fetchone()

        if running_row:
            return JsonResponse({'error': '이미 캡쳐가 진행 중입니다.'}, status=409)

    except Exception as e:
        return safe_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

    # 리테일러명 변환 (소문자)
    retailer_key = retailer.lower()
    created_id = request.user.username if request.user.is_authenticated else ''

    # SSM 명령 실행 (Task Scheduler 방식)
    try:
        ssm_client = boto3.client(
            'ssm',
            region_name=instance_region,
            aws_access_key_id=SSM_CONFIG['access_key'],
            aws_secret_access_key=SSM_CONFIG['secret_key']
        )

        # Task Scheduler 방식: 파라미터 파일 생성 후 task 실행
        task_name = 'capture_error'
        param_file = 'C:\\samsung_ds_retail_com\\monitoring\\capture_params.json'

        param_json = f'{{"retailer": "{retailer_key}", "crawl_date": "{crawl_date}", "created_id": "{created_id}"}}'

        commands = [
            f'Set-Content -Path "{param_file}" -Value \'{param_json}\' -Encoding UTF8',
            f'schtasks /run /tn "{task_name}"',
            f'Write-Output "Task {task_name} triggered with params: {param_json}"'
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

        # 캡쳐 로그 INSERT
        try:
            conn2 = get_ds_connection()
            cursor2 = conn2.cursor()
            cursor2.execute("""
                INSERT INTO ssd_crawl_db.ds_monitoring_capture_log
                (retailer_id, crawl_date, triggered_at, triggered_id, status)
                VALUES (%s, %s, %s, %s, 'running')
            """, (retailer_id, crawl_date, datetime.now(), created_id))
            conn2.commit()
            cursor2.close()
            conn2.close()
        except Exception:
            pass  # 로그 INSERT 실패해도 캡쳐는 진행

        return JsonResponse({
            'success': True,
            'message': f'스크린샷 캡쳐 작업이 트리거되었습니다.',
            'command_id': command_id,
            'instance_id': instance_id,
            'retailer': retailer,
            'crawl_date': crawl_date,
            'task_name': task_name
        })

    except Exception as e:
        return safe_error(e)


@require_http_methods(["GET"])
def report_file_size_history(request):
    """
    최근 7일간 리테일러별 파일 용량 조회

    GET 파라미터:
    - end_date: 기준일 (YYYY-MM-DD), 기본값: 어제
    - days: 조회 일수 (기본값: 7)

    반환: {
        'dates': ['2026-01-28', '2026-01-29', ...],
        'retailers': [
            {'retailer': 'amazon_usa', 'sizes': [13480, 13608, ...], 'avg': 13550},
            ...
        ]
    }
    """
    end_date_str = request.GET.get('end_date')
    try:
        days = max(1, min(int(request.GET.get('days', 7)), 90))
    except (ValueError, TypeError):
        days = 7

    if end_date_str:
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
    else:
        end_date = date.today() - timedelta(days=1)

    start_date = end_date - timedelta(days=days - 1)

    conn = None
    cursor = None
    try:
        conn = get_ds_connection()
        cursor = conn.cursor()

        # 날짜 목록 생성
        dates = []
        current = start_date
        while current <= end_date:
            dates.append(current.strftime('%Y-%m-%d'))
            current += timedelta(days=1)

        # 리테일러별 파일 용량 조회 (sort_order 순서)
        cursor.execute("""
            SELECT t.retailer, d.crawl_date, d.file_size
            FROM ssd_crawl_db.ds_monitoring_report_daily d
            JOIN ssd_crawl_db.ds_monitoring_targets t ON d.retailer_id = t.retailer_id
            WHERE d.crawl_date BETWEEN %s AND %s AND d.is_del = 0
            ORDER BY t.sort_order, t.retailer, d.crawl_date
        """, (start_date, end_date))
        rows = cursor.fetchall()

        # 리테일러별로 그룹화
        retailer_data = {}
        retailer_order = []

        for retailer, crawl_date, file_size in rows:
            if retailer not in retailer_data:
                retailer_data[retailer] = {}
                retailer_order.append(retailer)
            # crawl_date가 문자열이면 그대로, date 객체면 변환
            date_key = crawl_date if isinstance(crawl_date, str) else crawl_date.strftime('%Y-%m-%d')
            retailer_data[retailer][date_key] = file_size or 0

        # 결과 포맷
        retailers = []
        for retailer in retailer_order:
            sizes = [retailer_data[retailer].get(d, 0) for d in dates]
            valid_sizes = [s for s in sizes if s > 0]
            avg = round(sum(valid_sizes) / len(valid_sizes)) if valid_sizes else 0
            retailers.append({
                'retailer': retailer,
                'sizes': sizes,
                'avg': avg
            })

        return JsonResponse({
            'dates': dates,
            'retailers': retailers
        })

    except Exception as e:
        return safe_error(e, 'db')
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@require_http_methods(["GET"])
def screenshot_status(request):
    """리테일러별 스크린샷 캡쳐 상태 조회 API"""
    retailer = request.GET.get('retailer')
    crawl_date = request.GET.get('crawl_date')

    if not retailer or not crawl_date:
        return JsonResponse({'error': '리테일러와 날짜가 필요합니다.'}, status=400)

    conn = None
    cursor = None
    try:
        conn = get_ds_connection()
        cursor = conn.cursor()

        # 스크린샷 캡쳐 현황
        cursor.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN a.screenshot_id IS NOT NULL THEN 1 ELSE 0 END) as captured
            FROM ssd_crawl_db.ds_monitoring_report_anomaly a
            JOIN ssd_crawl_db.ds_monitoring_targets t ON a.retailer_id = t.retailer_id
            WHERE LOWER(t.retailer) = LOWER(%s) AND a.crawl_date = %s AND a.is_del = 0
        """, (retailer, crawl_date))

        row = cursor.fetchone()
        total = row[0] or 0
        captured = row[1] or 0
        completed = total > 0 and total == captured

        # 캡쳐 로그 처리
        is_running = False
        triggered_at = None

        # running 로그 확인
        cursor.execute("""
            SELECT cl.id, cl.triggered_at
            FROM ssd_crawl_db.ds_monitoring_capture_log cl
            JOIN ssd_crawl_db.ds_monitoring_targets t ON cl.retailer_id = t.retailer_id
            WHERE LOWER(t.retailer) = LOWER(%s) AND cl.crawl_date = %s AND cl.status = 'running'
            ORDER BY cl.triggered_at DESC LIMIT 1
        """, (retailer, crawl_date))
        log_row = cursor.fetchone()

        if log_row:
            is_running = True
            triggered_at = log_row[1].strftime('%Y-%m-%d %H:%M:%S') if log_row[1] else None

        return JsonResponse({
            'retailer': retailer,
            'total': total,
            'captured': captured,
            'remaining': total - captured,
            'completed': completed,
            'is_running': is_running,
            'triggered_at': triggered_at
        })

    except Exception as e:
        return safe_error(e, 'db')
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def screenshot_delete(request):
    """스크린샷 삭제 API (anomaly screenshot_id NULL + file soft delete + S3 삭제)"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST 요청만 허용됩니다.'}, status=405)

    try:
        body = json.loads(request.body)
        anomaly_ids = body.get('anomaly_ids', [])

        if not anomaly_ids:
            return JsonResponse({'success': False, 'error': 'anomaly_ids가 필요합니다.'})

        conn = get_ds_connection()
        cursor = conn.cursor()

        # 1. anomaly에서 screenshot_id 목록 조회
        placeholders = ','.join(['%s'] * len(anomaly_ids))
        cursor.execute(f"""
            SELECT id, screenshot_id FROM ssd_crawl_db.ds_monitoring_report_anomaly
            WHERE id IN ({placeholders}) AND screenshot_id IS NOT NULL AND is_del = 0
        """, anomaly_ids)
        anomaly_rows = cursor.fetchall()

        if not anomaly_rows:
            cursor.close()
            conn.close()
            return JsonResponse({'success': False, 'error': '삭제할 스크린샷이 없습니다.'})

        screenshot_ids = [row[1] for row in anomaly_rows]
        target_anomaly_ids = [row[0] for row in anomaly_rows]

        # 2. file 테이블에서 파일 정보 조회
        file_placeholders = ','.join(['%s'] * len(screenshot_ids))
        cursor.execute(f"""
            SELECT file_id, file_path, file_name FROM ssd_crawl_db.ds_monitoring_file
            WHERE file_id IN ({file_placeholders}) AND is_del = 0
        """, screenshot_ids)
        file_rows = cursor.fetchall()

        # 3. S3 파일 삭제
        if file_rows:
            try:
                s3_client = boto3.client(
                    's3',
                    region_name=S3_CONFIG['region'],
                    aws_access_key_id=S3_CONFIG['access_key'],
                    aws_secret_access_key=S3_CONFIG['secret_key']
                )
                for f in file_rows:
                    s3_key = f'{f[1].rstrip("/")}/{f[2]}'
                    s3_client.delete_object(Bucket=S3_CONFIG['bucket'], Key=s3_key)
            except Exception:
                pass

        # 4. file 테이블 soft delete
        cursor.execute(f"""
            UPDATE ssd_crawl_db.ds_monitoring_file
            SET is_del = 1
            WHERE file_id IN ({file_placeholders})
        """, screenshot_ids)

        # 5. anomaly 테이블 screenshot_id = NULL
        anomaly_placeholders = ','.join(['%s'] * len(target_anomaly_ids))
        cursor.execute(f"""
            UPDATE ssd_crawl_db.ds_monitoring_report_anomaly
            SET screenshot_id = NULL
            WHERE id IN ({anomaly_placeholders})
        """, target_anomaly_ids)

        conn.commit()
        cursor.close()
        conn.close()

        return JsonResponse({'success': True, 'deleted_count': len(target_anomaly_ids)})

    except Exception as e:
        return safe_error(e, success=False)


def screenshot_upload(request):
    """스크린샷 수동 업로드 API (파일 → S3 업로드 → DB 등록 → anomaly 연결)"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST 요청만 허용됩니다.'}, status=405)

    try:
        uploaded_file = request.FILES.get('file')
        anomaly_id = request.POST.get('anomaly_id')

        if not uploaded_file or not anomaly_id:
            return JsonResponse({'success': False, 'error': '파일과 anomaly_id가 필요합니다.'})

        # 파일 검증
        allowed_types = ('image/png', 'image/jpeg')
        if uploaded_file.content_type not in allowed_types:
            return JsonResponse({'success': False, 'error': 'PNG 또는 JPG 파일만 업로드할 수 있습니다.'})

        max_size = 10 * 1024 * 1024  # 10MB
        if uploaded_file.size > max_size:
            return JsonResponse({'success': False, 'error': '파일 크기가 10MB를 초과합니다.'})

        anomaly_id = int(anomaly_id)

        conn = get_ds_connection()
        cursor = conn.cursor()

        # anomaly 조회 → retailer, crawl_date, retailersku 추출
        cursor.execute("""
            SELECT a.id, t.retailer, a.crawl_date, a.retailersku
            FROM ssd_crawl_db.ds_monitoring_report_anomaly a
            LEFT JOIN ssd_crawl_db.ds_monitoring_targets t ON a.retailer_id = t.retailer_id
            WHERE a.id = %s AND a.is_del = 0
        """, (anomaly_id,))
        row = cursor.fetchone()

        if not row:
            cursor.close()
            conn.close()
            return JsonResponse({'success': False, 'error': '해당 이상치를 찾을 수 없습니다.'})

        retailer = row[1]
        crawl_date = row[2]  # date 객체
        retailersku = row[3]
        if isinstance(crawl_date, str):
            crawl_date = datetime.strptime(crawl_date, '%Y-%m-%d').date()

        # S3 키 생성 (캡쳐 프로그램과 동일 패턴: {retailer}_{retailersku}_{timestamp}.png)
        # 캡쳐 프로그램은 소문자 retailer를 사용하므로 동일하게 소문자 변환
        retailer_lower = retailer.lower()
        now = datetime.now()
        year = crawl_date.strftime('%Y')
        year_month = crawl_date.strftime('%Y%m')
        year_month_day = crawl_date.strftime('%Y%m%d')
        creation_timestamp = now.strftime('%Y%m%d%H%M%S')
        if retailersku:
            file_name = f"{retailer_lower}_{retailersku}_{creation_timestamp}.png"
        else:
            file_name = f"{retailer_lower}_{creation_timestamp}.png"
        file_path = f"{year}/{year_month}/{year_month_day}/{retailer_lower}/"
        s3_key = f"{file_path}{file_name}"

        # S3 업로드
        file_bytes = uploaded_file.read()
        s3_client = boto3.client(
            's3',
            region_name=S3_CONFIG['region'],
            aws_access_key_id=S3_CONFIG['access_key'],
            aws_secret_access_key=S3_CONFIG['secret_key']
        )
        s3_client.put_object(
            Bucket=S3_CONFIG['bucket'],
            Key=s3_key,
            Body=file_bytes,
            ContentType=uploaded_file.content_type
        )

        # ds_monitoring_file INSERT
        created_id = request.user.username if request.user.is_authenticated else ''
        cursor.execute("""
            INSERT INTO ssd_crawl_db.ds_monitoring_file
            (file_name, file_path, file_size, file_type, is_del, created_at, created_id)
            VALUES (%s, %s, %s, %s, 0, %s, %s)
        """, (file_name, file_path, len(file_bytes), uploaded_file.content_type, now, created_id))
        file_id = cursor.lastrowid

        # anomaly.screenshot_id 업데이트
        cursor.execute("""
            UPDATE ssd_crawl_db.ds_monitoring_report_anomaly
            SET screenshot_id = %s
            WHERE id = %s
        """, (file_id, anomaly_id))

        conn.commit()
        cursor.close()
        conn.close()

        return JsonResponse({'success': True, 'file_id': file_id})

    except ClientError as e:
        return safe_error(e, 's3', success=False)
    except Exception as e:
        return safe_error(e, success=False)
