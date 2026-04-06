from datetime import timedelta

from apps.common.db import dx_connection
from apps.common.dx_schedules import get_kst_time_info, get_schedule_kst_info
from apps.dx.dx_layer1.common.context import SECTION_TITLES
from . import market_trend_repositories as repo


def get_layer1_stats(cursor, target_date, now):
    """
    Market Trend Layer1 통계 검증
    - market_mst 기준 기대건수 vs market_trend 수집건수 비교
    - 키워드 커버리지 (등록 vs 수집)
    - TV/HHP 카테고리별 상세 데이터

    Returns: {'check': {...}, 'failed_items': []}
    """
    next_day = target_date + timedelta(days=1)

    market_trend_info = get_schedule_kst_info('market_trend', target_date, now)

    if not market_trend_info:
        kst_start = get_kst_time_info(23, target_date)
        market_trend_info = {
            'us_start_hour': 23,
            'collection_duration_min': 300,
            'kst_start': kst_start,
            'kst_end': {'full_display': f"{next_day} 18:00"},
            'time_status': None,
            'is_pending': False,
            'is_collecting': False,
            'collection_done': True
        }

    target_date_str = target_date.strftime('%Y-%m-%d')

    market_expected = repo.get_market_expected_counts(cursor)
    market_collected = repo.get_market_collected_counts(cursor, target_date_str)

    keyword_registered = repo.get_keyword_registered_counts(cursor)
    keyword_collected = repo.get_keyword_collected_counts(cursor, target_date_str)
    missing_keywords_by_pl = repo.get_missing_keywords(cursor, target_date_str)
    
    market_avg = repo.get_market_avg_counts(cursor, target_date_str)

    market_total_collected = 0
    market_total_expected = 0

    tv_market_items = []
    tv_market_total = 0
    tv_market_expected = 0

    hhp_market_items = []
    hhp_market_total = 0
    hhp_market_expected = 0

    content_order = {'Event': 0, 'News': 1}

    for key, expected in market_expected.items():
        product_line, content_type = key.split('_')
        collected = market_collected.get(key, 0)
        avg = market_avg.get(key, 0)

        if expected > 0:
            rate = (collected / expected) * 100
        else:
            rate = 0 if collected == 0 else 100

        if market_trend_info['is_pending']:
            status = 'PENDING'
        elif expected == 0:
            status = 'PENDING'
        elif rate >= 100:
            status = 'OK'
        elif market_trend_info['is_collecting']:
            status = 'COLLECTING'
        else:
            status = 'CRITICAL'

        market_total_collected += collected
        market_total_expected += expected

        item_data = {
            'name': content_type,
            'collected': collected,
            'expected': expected,
            'avg': avg,
            'rate': round(rate, 1),
            'status': status
        }

        if product_line == 'TV':
            tv_market_items.append(item_data)
            tv_market_total += collected
            tv_market_expected += expected
        else:
            hhp_market_items.append(item_data)
            hhp_market_total += collected
            hhp_market_expected += expected

    tv_market_items.sort(key=lambda x: content_order.get(x['name'], 99))
    hhp_market_items.sort(key=lambda x: content_order.get(x['name'], 99))

    if tv_market_expected > 0:
        tv_market_rate = (tv_market_total / tv_market_expected) * 100
    else:
        tv_market_rate = 0 if tv_market_total == 0 else 100

    if market_trend_info['is_pending']:
        tv_market_status = 'PENDING'
    elif tv_market_expected == 0:
        tv_market_status = 'PENDING'
    elif tv_market_rate >= 100:
        tv_market_status = 'OK'
    elif market_trend_info['is_collecting']:
        tv_market_status = 'COLLECTING'
    else:
        tv_market_status = 'CRITICAL'

    if hhp_market_expected > 0:
        hhp_market_rate = (hhp_market_total / hhp_market_expected) * 100
    else:
        hhp_market_rate = 0 if hhp_market_total == 0 else 100

    if market_trend_info['is_pending']:
        hhp_market_status = 'PENDING'
    elif hhp_market_expected == 0:
        hhp_market_status = 'PENDING'
    elif hhp_market_rate >= 100:
        hhp_market_status = 'OK'
    elif market_trend_info['is_collecting']:
        hhp_market_status = 'COLLECTING'
    else:
        hhp_market_status = 'CRITICAL'

    tv_kw_registered = keyword_registered.get('TV', 0)
    tv_kw_collected = keyword_collected.get('TV', 0)
    tv_kw_missing = missing_keywords_by_pl.get('TV', [])
    tv_kw_rate = round((tv_kw_collected / tv_kw_registered * 100), 1) if tv_kw_registered > 0 else 100

    hhp_kw_registered = keyword_registered.get('HHP', 0)
    hhp_kw_collected = keyword_collected.get('HHP', 0)
    hhp_kw_missing = missing_keywords_by_pl.get('HHP', [])
    hhp_kw_rate = round((hhp_kw_collected / hhp_kw_registered * 100), 1) if hhp_kw_registered > 0 else 100

    total_kw_registered = tv_kw_registered + hhp_kw_registered
    total_kw_collected = tv_kw_collected + hhp_kw_collected
    total_kw_missing = len(tv_kw_missing) + len(hhp_kw_missing)
    total_kw_rate = round((total_kw_collected / total_kw_registered * 100), 1) if total_kw_registered > 0 else 100

    def get_keyword_coverage_status(registered, collected, is_pending, is_collecting):
        if is_pending:
            return 'PENDING'
        if registered == 0:
            return 'PENDING'
        rate = (collected / registered) * 100
        if rate >= 100:
            return 'OK'
        elif is_collecting:
            return 'COLLECTING'
        else:
            return 'CRITICAL'

    tv_kw_status = get_keyword_coverage_status(
        tv_kw_registered, tv_kw_collected,
        market_trend_info['is_pending'], market_trend_info['is_collecting']
    )

    hhp_kw_status = get_keyword_coverage_status(
        hhp_kw_registered, hhp_kw_collected,
        market_trend_info['is_pending'], market_trend_info['is_collecting']
    )

    tv_market_data = {
        'name': 'TV',
        'total': tv_market_total,
        'expected': tv_market_expected,
        'rate': round(tv_market_rate, 1),
        'status': tv_kw_status,
        'items': tv_market_items,
        'keyword_coverage': {
            'registered': tv_kw_registered,
            'collected': tv_kw_collected,
            'missing_count': len(tv_kw_missing),
            'missing_keywords': tv_kw_missing[:10],
            'rate': tv_kw_rate,
            'status': tv_kw_status
        }
    }

    hhp_market_data = {
        'name': 'HHP',
        'total': hhp_market_total,
        'expected': hhp_market_expected,
        'rate': round(hhp_market_rate, 1),
        'status': hhp_kw_status,
        'items': hhp_market_items,
        'keyword_coverage': {
            'registered': hhp_kw_registered,
            'collected': hhp_kw_collected,
            'missing_count': len(hhp_kw_missing),
            'missing_keywords': hhp_kw_missing[:10],
            'rate': hhp_kw_rate,
            'status': hhp_kw_status
        }
    }

    market_overall_status = get_keyword_coverage_status(
        total_kw_registered, total_kw_collected,
        market_trend_info['is_pending'], market_trend_info['is_collecting']
    )

    if market_total_expected > 0:
        market_overall_rate = (market_total_collected / market_total_expected) * 100
    else:
        market_overall_rate = 0 if market_total_collected == 0 else 100

    market_ok_count = sum(1 for s in [tv_kw_status, hhp_kw_status] if s == 'OK')

    check = {
        'name': SECTION_TITLES['market_trend'],
        'description': f'{market_ok_count}/2 카테고리 정상',
        'actual': market_total_collected,
        'expected': market_total_expected,
        'rate': round(market_overall_rate, 1),
        'status': market_overall_status,
        'check_type': 'market_trend',
        'categories': [tv_market_data, hhp_market_data],
        'us_time': f'{target_date} {market_trend_info["us_start_hour"]:02d}:00',
        'kr_time': market_trend_info['kst_start']['full_display'],
        'kr_time_end': market_trend_info['kst_end']['full_display'],
        'is_dst': market_trend_info['kst_start']['is_dst'],
        'keyword_coverage': {
            'total_registered': total_kw_registered,
            'total_collected': total_kw_collected,
            'total_missing': total_kw_missing,
            'rate': total_kw_rate,
            'status': market_overall_status
        }
    }

    return {'check': check, 'failed_items': []}


def get_market_trend_raw_data(category, content_type, target_date):
    """
    Market Trend 원본 데이터 조회
    - category: TV 또는 HHP
    - content_type: Event, News 등 (빈 문자열이면 전체)
    - target_date: 조회 날짜 (date 객체)

    Returns: {'category': ..., 'content_type': ..., 'date': ..., 'columns': [...], 'data': [...], 'total_count': int}
    """
    target_date_str = target_date.strftime('%Y-%m-%d')
    with dx_connection() as (conn, cursor):
        columns, rows = repo.get_market_trend_raw_data_list(
            cursor, 
            target_date_str, 
            category, 
            content_type
        )
        
    return {
        'category': category,
        'content_type': content_type,
        'date': target_date_str,
        'columns': columns,
        'data': rows,
        'total_count': len(rows)
    }
