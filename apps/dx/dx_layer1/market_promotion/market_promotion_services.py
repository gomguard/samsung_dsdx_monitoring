from datetime import timedelta

from apps.common.db import dx_connection
from apps.common.dx_schedules import get_schedule_kst_info, get_kst_time_info
from apps.dx.dx_layer1.common.context import SECTION_TITLES
from . import market_promotion_repositories as repo


PROMO_RETAILERS = ['Amazon', 'Best Buy', 'Walmart', "Sam's Club", 'Home Depot', "Lowe's", 'Costco']


def get_layer1_stats(cursor, target_date, now):
    """
    Market Promotion 대시보드 통계 조회.
    Returns: {'check': {...}, 'failed_items': []}
    """
    failed_items = []

    is_monday = target_date.weekday() == 0

    days_until_monday = (7 - target_date.weekday()) % 7
    if days_until_monday == 0:
        days_until_monday = 7
    next_monday = target_date + timedelta(days=days_until_monday)

    market_promo_info = get_schedule_kst_info('market_promotion', target_date, now)

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

    promo_nine_weeks = target_date + timedelta(weeks=9)
    promo_event_count = repo.get_event_count_within_weeks(
        cursor, 
        target_date.strftime('%Y-%m-%d'), 
        promo_nine_weeks.strftime('%Y-%m-%d')
    )

    promo_retailer_counts = repo.get_collected_promotions_by_retailer(
        cursor,
        target_date.strftime('%Y-%m-%d')
    )

    promo_total_collected = sum(promo_retailer_counts.values())
    promo_expected = promo_event_count * len(PROMO_RETAILERS)

    promo_retailers = []
    promo_ok_count = 0
    for retailer in PROMO_RETAILERS:
        collected = promo_retailer_counts.get(retailer, 0)
        expected = promo_event_count

        if expected > 0:
            rate = (collected / expected) * 100
        else:
            rate = 0 if collected == 0 else 100

        if not is_monday:
            status = 'PENDING'
        elif promo_is_pending:
            status = 'PENDING'
        elif expected == 0:
            status = 'PENDING'
        elif rate >= 100:
            status = 'OK'
            promo_ok_count += 1
        elif promo_collection_done:
            if rate >= 90:
                status = 'WARNING'
            else:
                status = 'CRITICAL'
        else:
            status = 'COLLECTING'
            promo_is_collecting = True

        promo_retailers.append({
            'retailer': retailer,
            'collected': collected,
            'expected': expected,
            'rate': round(rate, 1),
            'status': status
        })

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
        promo_overall_status = 'OK'
        promo_description = f'{promo_ok_count}/{len(PROMO_RETAILERS)} 리테일러 정상'
    elif promo_collection_done:
        if promo_overall_rate >= 90:
            promo_overall_status = 'WARNING'
        else:
            promo_overall_status = 'CRITICAL'
        promo_description = f'{promo_ok_count}/{len(PROMO_RETAILERS)} 리테일러 정상'
    else:
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


def get_promotion_raw_data(retailer, target_date):
    """
    Market Promotion Raw Data 조회.
    Returns: {'date': str, 'analysis_date': str, 'retailer': str, 'columns': [], 'data': [], 'total_count': int}
    """
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

    with dx_connection() as (conn, cursor):
        columns, rows = repo.get_promotion_raw_data_list(
            cursor, 
            retailer, 
            analysis_monday.strftime('%Y-%m-%d')
        )

        results['columns'] = columns
        results['total_count'] = len(rows)
        results['data'] = rows

    return results
