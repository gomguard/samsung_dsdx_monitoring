from datetime import timedelta

from apps.common.dx_schedules import get_schedule_kst_info, get_kst_time_info
from apps.dx.dx_layer1.common.context import SECTION_TITLES


PROMO_RETAILERS = ['Amazon', 'Best Buy', 'Walmart', "Sam's Club", 'Home Depot', "Lowe's", 'Costco']


def get_layer1_stats(cursor, target_date, now):
    """
    Market Promotion 대시보드 통계 조회.
    Returns: {'check': {...}, 'failed_items': []}
    """
    failed_items = []

    # 조회 날짜가 월요일인지 확인 (0=월요일)
    is_monday = target_date.weekday() == 0

    # 다음 월요일 계산
    days_until_monday = (7 - target_date.weekday()) % 7
    if days_until_monday == 0:
        days_until_monday = 7  # 오늘이 월요일이면 다음 월요일
    next_monday = target_date + timedelta(days=days_until_monday)

    # DB에서 Market Promotion 스케줄 정보 가져오기 (KST 변환 포함)
    market_promo_info = get_schedule_kst_info('market_promotion', target_date, now)

    # market_promo_info가 None인 경우 기본값 사용
    if not market_promo_info:
        kst_start = get_kst_time_info(18, target_date)
        market_promo_info = {
            'us_start_hour': 18,
            'collection_duration_min': 30,
            'kst_start': kst_start,
            'kst_end': {'full_display': f"{kst_start['date']} {(kst_start['hour'] + 1) % 24:02d}:00"},
            'time_status': None,
            'is_pending': False,
            'is_collecting': False,
            'collection_done': True
        }

    promo_is_pending = market_promo_info['is_pending']
    promo_is_collecting = market_promo_info['is_collecting']
    promo_collection_done = market_promo_info['collection_done']

    # 9주 이내 이벤트 수 조회
    promo_nine_weeks = target_date + timedelta(weeks=9)
    cursor.execute("""
        SELECT COUNT(DISTINCT id)
        FROM openai_event_mst
        WHERE is_active = true
          AND event_date IS NOT NULL
          AND event_date > %s
          AND event_date <= %s
    """, (target_date.strftime('%Y-%m-%d'), promo_nine_weeks.strftime('%Y-%m-%d')))
    promo_event_count = cursor.fetchone()[0] or 0

    # 해당 날짜에 수집된 프로모션 데이터 조회
    cursor.execute("""
        SELECT
            p.retailer,
            COUNT(*) as cnt
        FROM openai_retailer_promotions p
        WHERE p.crawled_at = %s
        GROUP BY p.retailer
        ORDER BY p.retailer
    """, (target_date.strftime('%Y-%m-%d'),))
    promo_retailer_counts = {row[0]: row[1] for row in cursor.fetchall()}

    # 총 수집건수
    promo_total_collected = sum(promo_retailer_counts.values())

    # 예상 수집건수: 대상 이벤트 수 × 7개 리테일러
    promo_expected = promo_event_count * len(PROMO_RETAILERS)

    # 리테일러별 상세 데이터
    promo_retailers = []
    promo_ok_count = 0
    for retailer in PROMO_RETAILERS:
        collected = promo_retailer_counts.get(retailer, 0)
        expected = promo_event_count  # 각 리테일러별 이벤트 수만큼 기대

        if expected > 0:
            rate = (collected / expected) * 100
        else:
            rate = 0 if collected == 0 else 100

        # 상태 판정
        if not is_monday:
            status = 'PENDING'
        elif promo_is_pending:
            status = 'PENDING'
        elif expected == 0:
            status = 'PENDING'
        elif rate >= 100:
            # 100% 완료
            status = 'OK'
            promo_ok_count += 1
        elif promo_collection_done:
            # 수집 시간 경과 (30분 지남) + 100% 미만 → 결과 표시 (WARNING/CRITICAL)
            if rate >= 90:
                status = 'WARNING'
            else:
                status = 'CRITICAL'
        else:
            # 수집 중 (100% 미만이고 30분 미경과)
            status = 'COLLECTING'
            promo_is_collecting = True

        promo_retailers.append({
            'retailer': retailer,
            'collected': collected,
            'expected': expected,
            'rate': round(rate, 1),
            'status': status
        })

    # 전체 상태
    if promo_expected > 0:
        promo_overall_rate = (promo_total_collected / promo_expected) * 100
    else:
        promo_overall_rate = 0 if promo_total_collected == 0 else 100

    if not is_monday:
        promo_overall_status = 'PENDING'
        promo_description = '분석대상일 아님'
    elif promo_is_pending:
        promo_overall_status = 'PENDING'
        promo_description = f'대기중'
    elif promo_expected == 0:
        promo_overall_status = 'PENDING'
        promo_description = '대상 이벤트 없음'
    elif promo_overall_rate >= 100:
        # 100% 완료
        promo_overall_status = 'OK'
        promo_description = f'{promo_ok_count}/{len(PROMO_RETAILERS)} 리테일러 정상'
    elif promo_collection_done:
        # 수집 시간 경과 (30분 지남) + 100% 미만 → 결과 표시
        if promo_overall_rate >= 90:
            promo_overall_status = 'WARNING'
        else:
            promo_overall_status = 'CRITICAL'
        promo_description = f'{promo_ok_count}/{len(PROMO_RETAILERS)} 리테일러 정상'
    else:
        # 수집 중 (100% 미만이고 30분 미경과)
        promo_overall_status = 'COLLECTING'
        promo_description = f'수집중 ({round(promo_overall_rate, 1)}%)'

    check = {
        'name': SECTION_TITLES['market_promotion'],
        'description': promo_description,
        'actual': promo_total_collected,
        'expected': promo_expected,
        'rate': round(promo_overall_rate, 1),
        'status': promo_overall_status,
        'check_type': 'market_promotion',
        'retailers': promo_retailers,
        'event_count': promo_event_count,
        'is_target_date': is_monday,
        'next_target_date': str(next_monday) if not is_monday else None,
        'us_time': f'{target_date} {market_promo_info["us_start_hour"]:02d}:00',
        'kr_time': market_promo_info['kst_start']['full_display'],
        'kr_time_end': market_promo_info['kst_end']['full_display'],
        'is_dst': market_promo_info['kst_start']['is_dst']
    }

    return {'check': check, 'failed_items': failed_items}


def get_promotion_raw_data(cursor, retailer, target_date):
    """
    Market Promotion Raw Data 조회.
    Returns: {'date': str, 'analysis_date': str, 'retailer': str, 'columns': [], 'data': [], 'total_count': int}
    """
    # 분석대상일(월요일) 계산
    days_since_monday = target_date.weekday()
    analysis_monday = target_date - timedelta(days=days_since_monday)

    results = {
        'date': str(target_date),
        'analysis_date': str(analysis_monday),
        'retailer': retailer,
        'columns': [],
        'data': [],
        'total_count': 0
    }

    columns = [
        'id', 'event_name', 'event_date', 'event_week',
        'retailer', 'promo_start_date', 'promo_end_date',
        'source_url', 'crawled_at'
    ]

    query = """
        SELECT
            p.id,
            e.event_name,
            e.event_date,
            e.event_week,
            p.retailer,
            p.promo_start_date,
            p.promo_end_date,
            p.source_url,
            p.crawled_at
        FROM openai_retailer_promotions p
        LEFT JOIN openai_event_mst e ON p.event_id = e.id
        WHERE p.crawled_at = %s
    """

    params = [analysis_monday.strftime('%Y-%m-%d')]

    if retailer:
        query += " AND p.retailer = %s"
        params.append(retailer)

    query += " ORDER BY e.event_date, p.id"

    cursor.execute(query, params)

    rows = cursor.fetchall()

    total_count = len(rows)

    results['columns'] = columns
    results['total_count'] = total_count
    results['data'] = rows

    return results
