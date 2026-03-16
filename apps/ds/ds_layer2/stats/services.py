"""
DS Layer 2 Stats Service: 데이터 품질 검수 비즈니스 로직
날짜별 NULL 필드 현황 조회 및 상세 데이터 처리

검증 조건:
1. title이 NULL이거나 imageurl이 'https://'로 시작하지 않으면 → 기본 필드 NULL
2. title과 imageurl이 둘 다 유효할 때:
   - retailprice, ships_from, sold_by 3개 모두 NULL → 정상
   - retailprice, ships_from, sold_by 일부만 NULL → 비정상 (부분 NULL)
"""

from datetime import datetime, timedelta
from apps.common.db import ds_connection
from apps.common.targets import load_monitoring_targets, load_monitoring_targets_with_instance, format_time
from apps.common.response import log_error


def get_monitoring_targets():
    """CSV에서 모니터링 대상 목록 로드"""
    return load_monitoring_targets()


def get_batches_for_date(target_date):
    """특정 날짜의 배치 목록을 리테일러별로 그룹화하여 반환"""
    batches_by_retailer = {}

    try:
        with ds_connection() as (conn, cursor):
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


def get_layer_stats(target_date, batch_view):
    """DS Layer 2 전체 데이터 품질 통계"""
    data = {
        'timestamp': datetime.now().isoformat(),
        'date': str(target_date),
        'layer': 2,
        'data_source': 'ds',
        'results': [],
        'summary': {}
    }

    try:
        with ds_connection() as (conn, cursor):
            # 마감 여부 확인 → 마감된 날짜는 현황 테이블 스냅샷 사용
            from apps.ds.ds_layer4.report.services import is_report_closed
            close_result = is_report_closed(str(target_date), existing=(conn, cursor))
            is_closed = close_result.get('is_closed', False)
            closed_data = {}
            try:
                if is_closed:
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

    return data


def get_table_null_detail(target_date, table_name, error_type, page, page_size, start_time, end_time, sort_by, sort_order):
    """
    특정 테이블의 비정상 데이터 상세 조회

    error_type:
    - title_null: title이 NULL인 데이터 (imageurl 상관없이)
    - imageurl_null: imageurl이 NULL인 데이터 (title 상관없이)
    - imageurl_invalid: title 유효, imageurl이 있지만 형식 오류
    - partial_null: title/imageurl 유효, retailprice/ships_from/sold_by 일부만 NULL
    """
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
        with ds_connection() as (conn, cursor):
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

    return data
