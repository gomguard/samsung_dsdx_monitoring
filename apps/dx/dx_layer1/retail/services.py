"""
Layer 1 Retail 서비스 — 비즈니스 로직 (HTTP 레이어 분리)
- dashboard/api.py, retail/api.py에서 추출한 순수 로직
"""

import re
from datetime import datetime, timedelta
from apps.common.retail_columns import get_retailer_columns, get_all_retailer_columns
from apps.common.response import log_error
from apps.dx.dx_layer1.common.context import SECTION_TITLES
from apps.common.dx_schedules import get_retail_time_slots, get_kst_time_info, get_schedule_kst_info


# 리테일러 설정
RETAILERS = ['amazon', 'bestbuy', 'walmart']
EXPECTED_PER_RETAILER = 300  # 기대값
OK_THRESHOLD = 200           # 정상 기준 (200개 이상이면 OK, 미만이면 CRITICAL)

# SQL Injection 방지용 화이트리스트
ALLOWED_TABLES = {'tv_retail_com', 'hhp_retail_com'}
ALLOWED_DATE_FIELDS = {'crawl_datetime::timestamp', 'crawl_strdatetime::timestamp'}
ALLOWED_RANK_FIELDS = {'promotion_position', 'trend_rank'}


def check_retailer_data(rows, category='TV'):
    """
    리테일러별 데이터 검증
    Returns: (retailer_details, total_count, all_ok)

    rows 형식:
    - TV: (account_name, cnt, main_count, bsr_count, promotion_count)
    - HHP: (account_name, cnt, main_count, bsr_count, trend_count)
    """
    retailer_counts = {r.lower(): {'count': 0, 'main': 0, 'bsr': 0, 'extra': 0} for r in RETAILERS}

    # 수집된 데이터 카운트
    for row in rows:
        retailer_name = row[0].lower() if row[0] else ''
        count = row[1]
        if retailer_name in retailer_counts:
            retailer_counts[retailer_name] = {
                'count': count,
                'main': row[2] if len(row) > 2 else 0,
                'bsr': row[3] if len(row) > 3 else 0,
                'extra': row[4] if len(row) > 4 else 0  # TV: promotion_rank (Bestbuy만), HHP: trend_rank
            }

    retailer_details = []
    total_count = 0
    statuses = []

    for retailer in RETAILERS:
        data = retailer_counts[retailer]
        count = data['count']
        total_count += count

        # 상태 판정: 200 이상 = OK, 200 미만 = CRITICAL
        if count >= OK_THRESHOLD:
            status = 'OK'
        else:
            status = 'CRITICAL'

        statuses.append(status)

        # 수집 항목 정보 구성 (카테고리 및 리테일러에 따라 다름)
        if category == 'TV':
            # TV: Amazon, Walmart는 main_rank, bsr_rank만 / Bestbuy는 promotion_position
            if retailer == 'bestbuy':
                items = [
                    {'name': 'Main Rank', 'count': data['main']},
                    {'name': 'BSR Rank', 'count': data['bsr']},
                    {'name': 'Promotion Position', 'count': data['extra']}
                ]
            else:
                items = [
                    {'name': 'Main Rank', 'count': data['main']},
                    {'name': 'BSR Rank', 'count': data['bsr']}
                ]
        else:
            # HHP: Amazon, Walmart는 main_rank, bsr_rank만 / Bestbuy는 trend_rank
            if retailer == 'bestbuy':
                items = [
                    {'name': 'Main Rank', 'count': data['main']},
                    {'name': 'BSR Rank', 'count': data['bsr']},
                    {'name': 'Trend Rank', 'count': data['extra']}
                ]
            else:
                items = [
                    {'name': 'Main Rank', 'count': data['main']},
                    {'name': 'BSR Rank', 'count': data['bsr']}
                ]

        retailer_details.append({
            'retailer': retailer.capitalize(),
            'count': count,
            'expected': EXPECTED_PER_RETAILER,
            'ok_threshold': OK_THRESHOLD,
            'status': status,
            'items': items
        })

    # 전체 상태 결정
    if 'CRITICAL' in statuses:
        overall_status = 'CRITICAL'
    else:
        overall_status = 'OK'

    return retailer_details, total_count, overall_status


def get_layer1_stats(cursor, target_date, now):
    """
    Layer 1 대시보드 - Retail 섹션 통계
    dashboard/api.py layer_stats()의 retail 섹션 로직 추출

    Args:
        cursor: DB 커서 (DX PostgreSQL)
        target_date: 조회 대상 날짜 (date 객체)
        now: 현재 시각 (datetime 객체)

    Returns:
        dict: {'check': {...}, 'failed_items': [...]}
    """
    next_day = target_date + timedelta(days=1)
    failed_items = []

    # ============================================================
    # 시간대 정의 - DB에서 로드
    # ============================================================

    # DB에서 시간대 슬롯 정보 가져오기 (TV/HHP 공통으로 사용)
    time_slots = get_retail_time_slots('TV', target_date)

    # ============================================================
    # TV Retail 검증 (통합)
    # ============================================================
    tv_time_slots = []
    tv_total_count = 0
    tv_slot_statuses = []

    for slot in time_slots:
        # TV는 main_rank, bsr_rank, promotion_position (Bestbuy만) 수집
        cursor.execute("""
            SELECT account_name,
                   COUNT(*) as cnt,
                   COUNT(CASE WHEN main_rank IS NOT NULL THEN 1 END) as main_count,
                   COUNT(CASE WHEN bsr_rank IS NOT NULL THEN 1 END) as bsr_count,
                   COUNT(CASE WHEN promotion_position IS NOT NULL THEN 1 END) as promotion_count
            FROM tv_retail_com
            WHERE crawl_datetime::timestamp >= %s
            AND crawl_datetime::timestamp < %s
            GROUP BY account_name
        """, (slot['start'], slot['end']))

        rows = cursor.fetchall()

        if slot['is_pending']:
            # time_status가 COLLECTING이면 수집중, 아니면 대기중
            slot_display_status = slot['time_status'] if slot['time_status'] else 'PENDING'
            # 수집중일 때도 현재까지 수집된 데이터 표시
            retailer_details, total, _ = check_retailer_data(rows)
            tv_total_count += total  # PENDING/COLLECTING 상태에서도 수집량 합계에 포함
            tv_time_slots.append({
                'name': slot['name'],
                'us_time': slot['us_time'],
                'kr_time': slot['kr_time'],
                'is_dst': slot.get('is_dst', False),
                'total': total,
                'expected': EXPECTED_PER_RETAILER * len(RETAILERS),
                'status': slot_display_status,
                'retailers': retailer_details  # 수집중에도 리테일러 데이터 표시
            })
        else:
            retailer_details, total, slot_status = check_retailer_data(rows)
            tv_total_count += total
            tv_slot_statuses.append(slot_status)

            tv_time_slots.append({
                'name': slot['name'],
                'us_time': slot['us_time'],
                'kr_time': slot['kr_time'],
                'is_dst': slot.get('is_dst', False),
                'total': total,
                'expected': EXPECTED_PER_RETAILER * len(RETAILERS),
                'status': slot_status,
                'retailers': retailer_details
            })

            # 실패 항목 추가
            for r in retailer_details:
                if r['status'] != 'OK':
                    error_type = '수집 없음' if r['count'] == 0 else ('주의' if r['status'] == 'WARNING' else '수집량 부족')
                    failed_items.append({
                        'source': f"TV Retail - {r['retailer']}",
                        'error_type': error_type,
                        'expected': f">= {OK_THRESHOLD}",
                        'actual': r['count'],
                        'timestamp': f"TV {slot['name']}"
                    })

    # TV 전체 상태 결정
    # COLLECTING 상태가 있으면 전체도 COLLECTING
    tv_has_collecting = any(s['status'] == 'COLLECTING' for s in tv_time_slots)
    tv_all_pending = all(s['status'] == 'PENDING' for s in tv_time_slots)

    if 'CRITICAL' in tv_slot_statuses:
        tv_overall_status = 'CRITICAL'
    elif 'WARNING' in tv_slot_statuses:
        tv_overall_status = 'WARNING'
    elif not tv_slot_statuses and tv_has_collecting:
        tv_overall_status = 'COLLECTING'
    elif not tv_slot_statuses and tv_all_pending:
        tv_overall_status = 'PENDING'
    elif not tv_slot_statuses:
        tv_overall_status = 'PENDING'
    else:
        tv_overall_status = 'OK'

    # 활성 슬롯 수 계산 (PENDING, COLLECTING 제외)
    tv_active_slots = len([s for s in tv_time_slots if s['status'] not in ['PENDING', 'COLLECTING']])
    tv_ok_slots = len([s for s in tv_time_slots if s['status'] == 'OK'])

    # TV Retail 데이터 (나중에 통합용으로 저장)
    tv_retail_data = {
        'name': 'TV',
        'total': tv_total_count,
        'expected': EXPECTED_PER_RETAILER * len(RETAILERS) * tv_active_slots,
        'status': tv_overall_status,
        'time_slots': tv_time_slots
    }

    # ============================================================
    # HHP Retail 검증 (통합)
    # ============================================================
    hhp_time_slots = []
    hhp_total_count = 0
    hhp_slot_statuses = []

    for slot in time_slots:
        # HHP도 main_rank, bsr_rank, trend_rank 수집
        cursor.execute("""
            SELECT account_name,
                   COUNT(*) as cnt,
                   COUNT(CASE WHEN main_rank IS NOT NULL THEN 1 END) as main_count,
                   COUNT(CASE WHEN bsr_rank IS NOT NULL THEN 1 END) as bsr_count,
                   COUNT(CASE WHEN trend_rank IS NOT NULL THEN 1 END) as trend_count
            FROM hhp_retail_com
            WHERE crawl_strdatetime::timestamp >= %s
            AND crawl_strdatetime::timestamp < %s
            GROUP BY account_name
        """, (slot['start'], slot['end']))

        rows = cursor.fetchall()

        if slot['is_pending']:
            # time_status가 COLLECTING이면 수집중, 아니면 대기중
            slot_display_status = slot['time_status'] if slot['time_status'] else 'PENDING'
            # 수집중일 때도 현재까지 수집된 데이터 표시
            retailer_details, total, _ = check_retailer_data(rows, category='HHP')
            hhp_total_count += total  # PENDING/COLLECTING 상태에서도 수집량 합계에 포함
            hhp_time_slots.append({
                'name': slot['name'],
                'us_time': slot['us_time'],
                'kr_time': slot['kr_time'],
                'is_dst': slot.get('is_dst', False),
                'total': total,
                'expected': EXPECTED_PER_RETAILER * len(RETAILERS),
                'status': slot_display_status,
                'retailers': retailer_details  # 수집중에도 리테일러 데이터 표시
            })
        else:
            retailer_details, total, slot_status = check_retailer_data(rows, category='HHP')
            hhp_total_count += total
            hhp_slot_statuses.append(slot_status)

            hhp_time_slots.append({
                'name': slot['name'],
                'us_time': slot['us_time'],
                'kr_time': slot['kr_time'],
                'is_dst': slot.get('is_dst', False),
                'total': total,
                'expected': EXPECTED_PER_RETAILER * len(RETAILERS),
                'status': slot_status,
                'retailers': retailer_details
            })

            for r in retailer_details:
                if r['status'] != 'OK':
                    error_type = '수집 없음' if r['count'] == 0 else ('주의' if r['status'] == 'WARNING' else '수집량 부족')
                    failed_items.append({
                        'source': f"HHP Retail - {r['retailer']}",
                        'error_type': error_type,
                        'expected': f">= {OK_THRESHOLD}",
                        'actual': r['count'],
                        'timestamp': f"HHP {slot['name']}"
                    })

    # HHP 전체 상태 결정
    # COLLECTING 상태가 있으면 전체도 COLLECTING
    hhp_has_collecting = any(s['status'] == 'COLLECTING' for s in hhp_time_slots)
    hhp_all_pending = all(s['status'] == 'PENDING' for s in hhp_time_slots)

    if 'CRITICAL' in hhp_slot_statuses:
        hhp_overall_status = 'CRITICAL'
    elif 'WARNING' in hhp_slot_statuses:
        hhp_overall_status = 'WARNING'
    elif not hhp_slot_statuses and hhp_has_collecting:
        hhp_overall_status = 'COLLECTING'
    elif not hhp_slot_statuses and hhp_all_pending:
        hhp_overall_status = 'PENDING'
    elif not hhp_slot_statuses:
        hhp_overall_status = 'PENDING'
    else:
        hhp_overall_status = 'OK'

    # 활성 슬롯 수 계산 (PENDING, COLLECTING 제외)
    hhp_active_slots = len([s for s in hhp_time_slots if s['status'] not in ['PENDING', 'COLLECTING']])
    hhp_ok_slots = len([s for s in hhp_time_slots if s['status'] == 'OK'])

    # HHP Retail 데이터
    hhp_retail_data = {
        'name': 'HHP',
        'total': hhp_total_count,
        'expected': EXPECTED_PER_RETAILER * len(RETAILERS) * hhp_active_slots,
        'status': hhp_overall_status,
        'time_slots': hhp_time_slots
    }

    # Retail 통합 (TV + HHP)
    total_retail_count = tv_total_count + hhp_total_count
    total_retail_expected = (tv_active_slots + hhp_active_slots) * EXPECTED_PER_RETAILER * len(RETAILERS)

    # 통합 상태 결정 (둘 중 더 나쁜 상태)
    status_priority = {'OK': 0, 'WARNING': 1, 'COLLECTING': 2, 'CRITICAL': 3, 'PENDING': 4}
    tv_priority = status_priority.get(tv_overall_status, 0)
    hhp_priority = status_priority.get(hhp_overall_status, 0)

    if tv_priority >= hhp_priority:
        total_retail_status = tv_overall_status
    else:
        total_retail_status = hhp_overall_status

    # 정상 카테고리 수 계산
    retail_ok_count = sum(1 for s in [tv_overall_status, hhp_overall_status] if s == 'OK')

    # 수집 시간 정보 (오전/오후) - US→KST 자동 변환 (날짜 포함)
    am_kst = get_kst_time_info(0, target_date)  # US 00:00
    pm_kst = get_kst_time_info(12, target_date)  # US 12:00

    # KST 날짜 계산
    am_kst_date = next_day if am_kst['next_day'] else target_date
    pm_kst_date = next_day if pm_kst['next_day'] else target_date

    retail_time_info = {
        'am': {
            'us': f'{target_date} 00:00',
            'kst': f'{am_kst_date} {am_kst["hour"]:02d}:00',
            'is_dst': am_kst['is_dst']
        },
        'pm': {
            'us': f'{target_date} 12:00',
            'kst': f'{pm_kst_date} {pm_kst["hour"]:02d}:00',
            'is_dst': pm_kst['is_dst']
        },
        'is_dst': am_kst['is_dst']  # 전체 서머타임 여부
    }

    check = {
        'name': SECTION_TITLES['retail'],
        'description': f'{retail_ok_count}/2 카테고리 정상',
        'actual': total_retail_count,
        'expected_min': total_retail_expected,
        'status': total_retail_status,
        'check_type': 'retail',
        'time_info': retail_time_info,
        'categories': [tv_retail_data, hhp_retail_data]
    }

    return {'check': check, 'failed_items': failed_items}


def get_retail_detail(cursor, target_date, product_line):
    """
    리테일 상세 현황 조회

    Args:
        cursor: DB 커서 (DX PostgreSQL)
        target_date: 조회 대상 날짜 (date 객체)
        product_line: 'tv' 또는 'hhp'

    Returns:
        dict: 리테일 상세 데이터
    """
    if product_line == 'tv':
        cursor.execute("""
            SELECT
                account_name as retailer,
                COUNT(*) as total,
                COUNT(CASE WHEN main_rank IS NOT NULL THEN 1 END) as main_count,
                COUNT(CASE WHEN bsr_rank IS NOT NULL THEN 1 END) as bsr_count,
                COUNT(CASE WHEN final_sku_price IS NOT NULL THEN 1 END) as price_count
            FROM tv_retail_com
            WHERE DATE(crawl_datetime::timestamp) = %s
            GROUP BY account_name
            ORDER BY account_name
        """, (target_date,))
    else:
        cursor.execute("""
            SELECT
                account_name as retailer,
                COUNT(*) as total,
                COUNT(CASE WHEN main_rank IS NOT NULL THEN 1 END) as main_count,
                COUNT(CASE WHEN bsr_rank IS NOT NULL THEN 1 END) as bsr_count,
                COUNT(CASE WHEN final_sku_price IS NOT NULL THEN 1 END) as price_count
            FROM hhp_retail_com
            WHERE DATE(crawl_strdatetime::timestamp) = %s
            GROUP BY account_name
            ORDER BY account_name
        """, (target_date,))

    rows = cursor.fetchall()

    results = []
    for row in rows:
        results.append({
            'retailer': row[0],
            'total': row[1],
            'main_count': row[2],
            'bsr_count': row[3],
            'price_count': row[4],
            'completeness': round((row[4] / row[1] * 100), 1) if row[1] > 0 else 0
        })

    return {
        'date': str(target_date),
        'product_line': product_line.upper(),
        'results': results,
        'total_retailers': len(results),
        'total_products': sum(r['total'] for r in results)
    }


def get_retail_summary(cursor, target_date, product_line):
    """
    Retail 상세 현황 - 리테일러x시간대x페이지타입별 테이블 + NULL 컬럼 현황

    Args:
        cursor: DB 커서 (DX PostgreSQL)
        target_date: 조회 대상 날짜 (date 객체)
        product_line: 'tv' 또는 'hhp'

    Returns:
        dict: 요약 데이터
    """
    next_day = target_date + timedelta(days=1)

    # 시간대 정의
    time_slots = [
        {'name': '오전', 'start': f'{target_date} 00:00:00', 'end': f'{target_date} 12:00:00'},
        {'name': '오후', 'start': f'{target_date} 12:00:00', 'end': f'{next_day} 00:00:00'}
    ]

    # 테이블명 및 날짜 필드 결정
    if product_line == 'tv':
        table_name = 'tv_retail_com'
        date_field = 'crawl_datetime::timestamp'
        extra_rank_field = 'promotion_position'
        extra_rank_name = 'Promotion'
    else:
        table_name = 'hhp_retail_com'
        date_field = 'crawl_strdatetime::timestamp'
        extra_rank_field = 'trend_rank'
        extra_rank_name = 'Trend'

    # 화이트리스트 검증
    if table_name not in ALLOWED_TABLES:
        raise ValueError(f"허용되지 않은 테이블: {table_name}")
    if date_field not in ALLOWED_DATE_FIELDS:
        raise ValueError(f"허용되지 않은 날짜 필드: {date_field}")
    if extra_rank_field not in ALLOWED_RANK_FIELDS:
        raise ValueError(f"허용되지 않은 랭크 필드: {extra_rank_field}")

    # 리테일러 목록
    retailers = ['Amazon', 'Bestbuy', 'Walmart']

    # 결과 데이터 구조
    summary_data = []
    null_columns_data = []
    total_check_count = 0  # 전체 검사 컬럼 수
    total_null_count = 0   # NULL 발생 컬럼 수

    # 리테일러별 컬럼 목록 - DB에서 로드
    # NULL 검사는 활성화된 컬럼만 대상으로 함

    column_checks_data = []  # 리테일러별 컬럼별 카운트 (체크 저장용)

    for retailer in retailers:
        retailer_rows = []
        retailer_null_cols = []
        retailer_total = 0
        # NULL 검사 대상 컬럼 (DB에서 활성 컬럼)
        check_columns = get_retailer_columns(product_line, retailer)
        # 컬럼명 화이트리스트 검증 — 영문/숫자/언더스코어만 허용
        for col in check_columns:
            if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', col):
                raise ValueError(f"허용되지 않은 컬럼명: {col}")
        retailer_check_slots = []

        for slot in time_slots:
            # 시간대별 페이지타입 카운트
            cursor.execute(f"""
                SELECT
                    COUNT(CASE WHEN page_type = 'main' OR main_rank IS NOT NULL THEN 1 END) as main_count,
                    COUNT(CASE WHEN page_type = 'bsr' OR bsr_rank IS NOT NULL THEN 1 END) as bsr_count,
                    COUNT(CASE WHEN {extra_rank_field} IS NOT NULL THEN 1 END) as extra_count,
                    COUNT(*) as total
                FROM {table_name}
                WHERE {date_field} >= %s
                AND {date_field} < %s
                AND LOWER(account_name) = LOWER(%s)
            """, (slot['start'], slot['end'], retailer))

            row = cursor.fetchone()
            main_count = row[0] or 0
            bsr_count = row[1] or 0
            extra_count = row[2] or 0
            total = row[3] or 0

            retailer_rows.append({
                'time_slot': slot['name'],
                'main': main_count,
                'bsr': bsr_count,
                'extra': extra_count,
                'extra_name': extra_rank_name,
                'total': total
            })
            retailer_total += total

            # NULL 컬럼 체크 - Layer 2와 동일한 방식 (COUNT로 한번에 조회)
            if total > 0 and check_columns:
                total_check_count += len(check_columns)
                count_parts = [f"COUNT({col}) as {col}_cnt" for col in check_columns]
                query = f"""
                    SELECT {', '.join(count_parts)}
                    FROM {table_name}
                    WHERE {date_field} >= %s
                    AND {date_field} < %s
                    AND LOWER(account_name) = LOWER(%s)
                """
                cursor.execute(query, (slot['start'], slot['end'], retailer))
                count_row = cursor.fetchone()
                if count_row:
                    # 컬럼별 카운트 저장
                    col_counts = {}
                    null_cols = []
                    for col, cnt in zip(check_columns, count_row):
                        col_counts[col] = cnt
                        if cnt == 0:
                            null_cols.append(col)

                    total_null_count += len(null_cols)

                    retailer_check_slots.append({
                        'time_slot': slot['name'],
                        'total': total,
                        'counts': col_counts
                    })

                    if null_cols:
                        retailer_null_cols.append({
                            'time_slot': slot['name'],
                            'null_columns': null_cols
                        })

        summary_data.append({
            'retailer': retailer,
            'rows': retailer_rows,
            'total': retailer_total
        })

        if retailer_null_cols:
            null_columns_data.append({
                'retailer': retailer,
                'time_slots': retailer_null_cols
            })

        if retailer_check_slots:
            column_checks_data.append({
                'retailer': retailer,
                'check_columns': check_columns,
                'time_slots': retailer_check_slots
            })

    # 전체 합계 계산
    grand_total = sum(r['total'] for r in summary_data)
    am_total = sum(r['rows'][0]['total'] for r in summary_data if r['rows'])
    pm_total = sum(r['rows'][1]['total'] for r in summary_data if len(r['rows']) > 1)

    return {
        'date': str(target_date),
        'product_line': product_line.upper(),
        'extra_rank_name': extra_rank_name,
        'summary': summary_data,
        'null_columns': null_columns_data,
        'totals': {
            'grand_total': grand_total,
            'am_total': am_total,
            'pm_total': pm_total
        },
        'check_stats': {
            'total_checks': total_check_count,
            'null_count': total_null_count
        },
        'column_checks': column_checks_data
    }


def get_retailer_raw_data(cursor, category, retailer, period, target_date):
    """
    리테일러별 원본 데이터 조회

    Args:
        cursor: DB 커서 (DX PostgreSQL)
        category: 'TV' 또는 'HHP'
        retailer: 'Amazon', 'Bestbuy', 'Walmart'
        period: '오전' 또는 '오후'
        target_date: 조회 대상 날짜 (date 객체)

    Returns:
        dict: 원본 데이터
    """
    next_day = target_date + timedelta(days=1)

    # 시간대 설정
    if period == '오전':
        start_time = f'{target_date} 00:00:00'
        end_time = f'{target_date} 12:00:00'
    else:
        start_time = f'{target_date} 12:00:00'
        end_time = f'{next_day} 00:00:00'

    results = {
        'category': category,
        'retailer': retailer,
        'period': period,
        'date': str(target_date),
        'columns': [],
        'data': []
    }

    try:
        # DB에서 해당 리테일러의 컬럼 목록 가져오기
        product_line = 'tv' if category == 'TV' else 'hhp'
        db_columns = get_retailer_columns(product_line, retailer)

        # id는 항상 맨 앞에 포함
        columns = ['id'] + [col for col in db_columns if col != 'id']

        if category == 'TV':
            date_column = 'crawl_datetime'
            table_name = 'tv_retail_com'
        else:
            date_column = 'crawl_strdatetime'
            table_name = 'hhp_retail_com'

        # 화이트리스트 검증
        if table_name not in ALLOWED_TABLES:
            raise ValueError(f"허용되지 않은 테이블: {table_name}")

        # 컬럼 검증 — DB에서 등록된 컬럼만 허용
        retailer_columns = get_all_retailer_columns(product_line)
        all_valid_columns = set()
        for cols in retailer_columns.values():
            all_valid_columns.update(cols)
        all_valid_columns.add('id')
        invalid_cols = [c for c in columns if c not in all_valid_columns]
        if invalid_cols:
            raise ValueError(f"허용되지 않은 컬럼: {invalid_cols}")

        query = f"""
            SELECT {', '.join(columns)}
            FROM {table_name}
            WHERE LOWER(account_name) = LOWER(%s)
            AND {date_column} >= %s
            AND {date_column} < %s
            ORDER BY id DESC
            LIMIT 500
        """

        cursor.execute(query, (retailer, start_time, end_time))
        rows = cursor.fetchall()

        results['columns'] = columns
        results['total_count'] = len(rows)
        results['data'] = rows

    except Exception as e:
        results['error'] = log_error(e)

    return results


def get_retailer_columns_info():
    """
    TV/HHP 리테일러별 수집 컬럼 정보 조회

    Returns:
        dict: TV/HHP 컬럼 정보
    """
    # DB에서 컬럼 정보 로드
    tv_columns = get_all_retailer_columns('tv')
    hhp_columns = get_all_retailer_columns('hhp')

    # 모든 컬럼 목록 (합집합) - 알파벳 순 정렬
    all_tv_columns = sorted(set(col for cols in tv_columns.values() for col in cols))
    all_hhp_columns = sorted(set(col for cols in hhp_columns.values() for col in cols))

    return {
        'tv': {
            'columns': tv_columns,
            'all_columns': all_tv_columns
        },
        'hhp': {
            'columns': hhp_columns,
            'all_columns': all_hhp_columns
        }
    }
