from datetime import timedelta
from decimal import Decimal

from apps.common.db import dx_connection
from apps.common.dx_schedules import get_kst_time_info, get_schedule_kst_info
from apps.dx.dx_layer1.common.context import SECTION_TITLES
from . import market_demand_repositories as repo


def get_layer1_stats(cursor, target_date, now):
    """
    Market 수요증감율 대시보드 통계.
    Returns {'check': {...}, 'failed_items': []}
    """
    is_monday = target_date.weekday() == 0  # 0=월
    days_until_monday = (7 - target_date.weekday()) % 7
    if days_until_monday == 0:
        days_until_monday = 7
    next_monday = target_date + timedelta(days=days_until_monday) if not is_monday else None
    next_day = target_date + timedelta(days=1)

    market_demand_info = get_schedule_kst_info('market_demand', target_date, now)

    if not market_demand_info:
        kst_start = get_kst_time_info(18, target_date)
        market_demand_info = {
            'us_start_hour': 18,
            'collection_duration_min': 300,
            'kst_start': kst_start,
            'kst_end': {'full_display': f"{next_day} 04:00"},
            'time_status': None,
            'is_pending': False,
            'is_collecting': False,
            'collection_done': True
        }

    demand_is_pending = market_demand_info['is_pending']
    demand_collection_done = market_demand_info['collection_done']

    def get_demand_stats(query_date):
        nine_weeks_later = query_date + timedelta(weeks=9)
        one_week_later = query_date + timedelta(weeks=1)

        str_query_date = query_date.strftime('%Y-%m-%d')
        str_nine_weeks = nine_weeks_later.strftime('%Y-%m-%d')
        str_one_week = one_week_later.strftime('%Y-%m-%d')

        target_by_category = repo.get_nine_weeks_later_keywords_count(cursor, str_query_date, str_nine_weeks)
        excluded_by_category = repo.get_one_week_later_keywords_count(cursor, str_query_date, str_one_week)
        result_by_category = repo.get_collected_keywords_count(cursor, str_query_date)

        return target_by_category, excluded_by_category, result_by_category

    target_demand, excluded_demand, result_demand = get_demand_stats(target_date)

    def calc_demand_status(result_cnt, target_cnt):
        if target_cnt == 0:
            return 0, 'OK' if result_cnt == 0 else 'CRITICAL'
        ratio = result_cnt / target_cnt
        if ratio >= 1.0:
            return round(ratio * 100, 1), 'OK'
        else:
            return round(ratio * 100, 1), 'CRITICAL'

    demand_categories = []
    demand_is_collecting = False
    for category in sorted(target_demand.keys()):
        target = target_demand.get(category, 0)
        result_cnt = result_demand.get(category, 0)
        completion_pct, base_status = calc_demand_status(result_cnt, target)

        if demand_is_pending:
            status = 'PENDING'
        elif completion_pct >= 100:
            status = 'OK'
        elif demand_collection_done:
            status = base_status
        else:
            status = 'COLLECTING'
            demand_is_collecting = True

        demand_categories.append({
            'category': category,
            'target': target,
            'collected': result_cnt,
            'rate': completion_pct,
            'status': status
        })

    demand_total_target = sum(c['target'] for c in demand_categories)
    demand_total_collected = sum(c['collected'] for c in demand_categories)
    demand_rate, _ = calc_demand_status(demand_total_collected, demand_total_target)
    demand_ok_count = len([c for c in demand_categories if c['status'] == 'OK'])

    if demand_is_pending:
        demand_overall_status = 'PENDING'
        demand_description = '대기중'
    elif demand_rate >= 100:
        demand_overall_status = 'OK'
        demand_description = f'{demand_ok_count}/{len(demand_categories)} 카테고리 정상'
    elif demand_collection_done:
        demand_overall_status = 'CRITICAL'
        demand_description = f'{demand_ok_count}/{len(demand_categories)} 카테고리 정상'
    else:
        demand_overall_status = 'COLLECTING'
        demand_description = f'수집중 ({demand_rate}%)'

    check = {
        'name': SECTION_TITLES['market_demand'],
        'description': demand_description,
        'status': demand_overall_status,
        'check_type': 'market_demand',
        'date': target_date.strftime('%Y-%m-%d'),
        'categories': demand_categories,
        'expected': demand_total_target,
        'total_target': demand_total_target,
        'actual': demand_total_collected,
        'total_collected': demand_total_collected,
        'rate': demand_rate,
        'us_time': f'{target_date} {market_demand_info["us_start_hour"]:02d}:00',
        'kr_time': market_demand_info['kst_start']['full_display'],
        'kr_time_end': market_demand_info['kst_end']['full_display'],
        'is_dst': market_demand_info['kst_start']['is_dst'],
        'is_target_date': is_monday,
        'next_target_date': str(next_monday) if next_monday else None
    }

    return {'check': check, 'failed_items': []}


def get_market_demand_raw_data(category, target_date):
    """
    Market 수요증감율 Raw Data 조회.
    Returns data dict with columns, data, total_count.
    """
    results = {
        'date': str(target_date),
        'category': category,
        'columns': [],
        'data': [],
        'total_count': 0
    }
    with dx_connection() as (conn, cursor):
        columns, processed = repo.get_raw_data_list(cursor, target_date.strftime('%Y-%m-%d'), category)
        
        results['columns'] = columns
        results['total_count'] = len(processed)
        results['data'] = processed

    return results


def get_missing_keywords(category, target_date):
    """
    Market 수요증감율 부족 키워드 상세 조회 (openai_keywords 기준).
    Returns data dict with missing_keywords, total_missing, summary.
    """
    results = {
        'date': str(target_date),
        'category': category,
        'missing_keywords': [],
        'total_missing': 0,
        'summary': {}
    }

    nine_weeks_later = target_date + timedelta(weeks=9)
    str_target_date = target_date.strftime('%Y-%m-%d')
    str_nine_weeks = nine_weeks_later.strftime('%Y-%m-%d')

    with dx_connection() as (conn, cursor):
        target_keywords = repo.get_target_keywords_list(cursor, str_target_date, str_nine_weeks, category)
        collected_set = repo.get_collected_events_set(cursor, str_target_date, category)

        missing_keywords = []
        summary_by_category = {}

        for row in target_keywords:
            cat, product_name, event_name, event_date = row
            key = (cat, product_name, event_name.upper())

            if cat not in summary_by_category:
                summary_by_category[cat] = {'total': 0, 'missing': 0}
            summary_by_category[cat]['total'] += 1

            if key not in collected_set:
                missing_keywords.append({
                    'category': cat,
                    'product_name': product_name,
                    'event_name': event_name,
                    'event_date': str(event_date)
                })
                summary_by_category[cat]['missing'] += 1

        results['missing_keywords'] = missing_keywords
        results['total_missing'] = len(missing_keywords)
        results['summary'] = summary_by_category

    return results
