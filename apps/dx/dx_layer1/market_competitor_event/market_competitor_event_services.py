from datetime import datetime, timedelta

from apps.common.db import dx_connection
from apps.dx.dx_layer1.common.context import SECTION_TITLES
from apps.dx.dx_layer1.common.quarter_utils import get_quarter_info, get_competitor_batch
from . import market_competitor_event_repositories as repo


def get_layer1_stats(cursor, target_date, now, comp_batch_id=None):
    """
    Market Competitor Event 대시보드 검증 통계.
    comp_batch_id가 None이면 quarter_utils로 직접 조회.
    Returns {'check': {...}, 'failed_items': []}
    """
    q_info = get_quarter_info(target_date)
    quarter_start = q_info['quarter_start']
    quarter_end = q_info['quarter_end']

    if comp_batch_id is None:
        comp_batch_id, _ = get_competitor_batch(cursor, quarter_start, quarter_end)

    first_day_of_month = target_date.replace(day=1)
    days_until_monday = (7 - first_day_of_month.weekday()) % 7
    if first_day_of_month.weekday() == 0:
        first_monday = first_day_of_month
    else:
        first_monday = first_day_of_month + timedelta(days=days_until_monday)

    is_first_monday = (target_date == first_monday)

    if target_date.month == 12:
        next_month_first_day = target_date.replace(year=target_date.year + 1, month=1, day=1)
    else:
        next_month_first_day = target_date.replace(month=target_date.month + 1, day=1)
    next_days_until_monday = (7 - next_month_first_day.weekday()) % 7
    if next_month_first_day.weekday() == 0:
        next_first_monday = next_month_first_day
    else:
        next_first_monday = next_month_first_day + timedelta(days=next_days_until_monday)

    month_start = first_day_of_month.strftime('%Y-%m-%d')
    if target_date.month == 12:
        month_end_date = target_date.replace(year=target_date.year + 1, month=1, day=1) - timedelta(days=1)
    else:
        month_end_date = target_date.replace(month=target_date.month + 1, day=1) - timedelta(days=1)
    month_end = month_end_date.strftime('%Y-%m-%d')
    month_name = target_date.strftime('%Y년 %m월')

    event_batch_row = repo.get_recent_event_batch_id(cursor, month_start, month_end)
    event_batch_id = event_batch_row[0] if event_batch_row else None
    event_last_run = event_batch_row[1] if event_batch_row else None

    event_collected = repo.get_event_collected_count(cursor, event_batch_id)
    event_expected = repo.get_expected_event_count(cursor, comp_batch_id)

    event_expected_combos = repo.get_expected_event_combos(cursor, comp_batch_id)
    event_collected_combos = repo.get_collected_event_combos(cursor, event_batch_id)

    event_keyword_coverage = {}
    for pl in ['TV', 'HHP']:
        expected_combos = event_expected_combos.get(pl, set())
        collected_combos = event_collected_combos.get(pl, set())
        missing_combos = expected_combos - collected_combos

        combo_rate = round((len(collected_combos) / len(expected_combos) * 100), 1) if len(expected_combos) > 0 else 100

        event_keyword_coverage[pl] = {
            'combo_expected': len(expected_combos),
            'combo_collected': len(collected_combos),
            'combo_missing': len(missing_combos),
            'combo_rate': combo_rate,
            'missing_samples': list(missing_combos)[:5]
        }

    event_categories = []
    event_total_collected = 0
    event_total_expected = 0
    event_statuses = []
    failed_items = []

    for category in ['TV', 'HHP']:
        collected = event_collected.get(category, 0)
        expected = event_expected.get(category, 0)
        kw_cov = event_keyword_coverage.get(category, {})

        if expected > 0:
            rate = (collected / expected) * 100
        else:
            rate = 0 if collected == 0 else 100

        combo_rate = kw_cov.get('combo_rate', 100)

        if not is_first_monday:
            status = 'PENDING'
        elif expected == 0:
            status = 'PENDING'
        elif combo_rate >= 100:
            status = 'OK'
        elif combo_rate >= 90:
            status = 'WARNING'
        else:
            status = 'CRITICAL'

        event_statuses.append(status)
        event_total_collected += collected
        event_total_expected += expected

        event_categories.append({
            'category': category,
            'collected': collected,
            'expected': expected,
            'rate': round(rate, 1),
            'status': status,
            'keyword_coverage': kw_cov
        })

        if status in ('WARNING', 'CRITICAL'):
            error_type = '커버리지 미달' if status == 'CRITICAL' else '주의'
            failed_items.append({
                'source': f"Market Competitor Event - {category}",
                'error_type': error_type,
                'expected': expected,
                'actual': collected,
                'timestamp': f"커버리지 {combo_rate}%",
                'status': status,
                'combo_rate': combo_rate
            })

    total_event_combo_expected = sum(kw.get('combo_expected', 0) for kw in event_keyword_coverage.values())
    total_event_combo_collected = sum(kw.get('combo_collected', 0) for kw in event_keyword_coverage.values())
    total_event_combo_rate = round((total_event_combo_collected / total_event_combo_expected * 100), 1) if total_event_combo_expected > 0 else 100
    total_event_combo_missing = sum(kw.get('combo_missing', 0) for kw in event_keyword_coverage.values())

    if not is_first_monday:
        event_overall_status = 'PENDING'
    elif total_event_combo_expected == 0:
        event_overall_status = 'PENDING'
    elif total_event_combo_rate >= 100:
        event_overall_status = 'OK'
    elif total_event_combo_rate >= 90:
        event_overall_status = 'WARNING'
    else:
        event_overall_status = 'CRITICAL'

    if event_total_expected > 0:
        event_overall_rate = (event_total_collected / event_total_expected) * 100
    else:
        event_overall_rate = 0 if event_total_collected == 0 else 100

    event_ok_count = len([s for s in event_statuses if s == 'OK'])

    if not is_first_monday:
        event_description = '분석대상일 아님'
    else:
        event_description = f'{event_ok_count}/{len(event_statuses)} 카테고리 정상'

    check = {
        'name': SECTION_TITLES['market_competitor_event'],
        'description': event_description,
        'actual': event_total_collected,
        'expected': event_total_expected,
        'rate': round(event_overall_rate, 1),
        'status': event_overall_status,
        'check_type': 'market_competitor_event',
        'categories': event_categories,
        'batch_id': event_batch_id,
        'last_run': event_last_run.isoformat() if event_last_run else None,
        'month': {
            'name': month_name,
            'start': month_start,
            'end': month_end,
            'first_monday': first_monday.strftime('%Y-%m-%d'),
            'next_first_monday': next_first_monday.strftime('%Y-%m-%d')
        },
        'is_target_date': is_first_monday,
        'keyword_coverage': {
            'total_combo_expected': total_event_combo_expected,
            'total_combo_collected': total_event_combo_collected,
            'total_combo_rate': total_event_combo_rate,
            'total_missing': total_event_combo_missing
        }
    }

    return {
        'check': check,
        'failed_items': failed_items,
    }


def get_competitor_event_raw_data(category, target_date):
    """Market Competitor Event Raw Data 조회"""
    month_start = target_date.replace(day=1)
    if target_date.month == 12:
        month_end = target_date.replace(year=target_date.year + 1, month=1, day=1) - timedelta(days=1)
    else:
        month_end = target_date.replace(month=target_date.month + 1, day=1) - timedelta(days=1)

    empty_columns = [
        'category', 'comp_brand', 'comp_sku_name', 'comp_launch_date',
        'comp_preorder', 'comp_pre_order_start_date', 'comp_preorder_end_date',
        'rumor_release_window', 'rumor_preorder_window', 'rumor_confidence_level',
        'calender_week', 'created_at'
    ]

    results = {
        'date': str(target_date),
        'category': category,
        'columns': [],
        'data': [],
        'total_count': 0,
    }

    with dx_connection() as (conn, cursor):
        batch_row = repo.get_recent_event_batch_id(cursor, str(month_start), str(month_end))

        if not batch_row:
            results['columns'] = empty_columns
            return results

        batch_id = batch_row[0]
        results['batch_id'] = batch_id

        columns, data = repo.get_competitor_event_raw_data_list(cursor, batch_id, category)

        results['columns'] = columns
        results['data'] = data
        results['total_count'] = len(data)

    return results


def get_missing_keywords(category, target_date):
    """Market Competitor Event 부족 키워드 조회"""
    month_start = target_date.replace(day=1)
    if target_date.month == 12:
        month_end = target_date.replace(year=target_date.year + 1, month=1, day=1) - timedelta(days=1)
    else:
        month_end = target_date.replace(month=target_date.month + 1, day=1) - timedelta(days=1)

    results = {
        'date': str(target_date),
        'category': category,
        'missing_keywords': [],
        'summary': {}
    }

    cats = ['TV', 'HHP'] if category == 'all' else [category]

    with dx_connection() as (conn, cursor):
        event_batch_row = repo.get_recent_event_batch_id(cursor, str(month_start), str(month_end))
        event_batch_id = event_batch_row[0] if event_batch_row else None

        q_info = get_quarter_info(target_date)
        comp_batch_id, _ = get_competitor_batch(cursor, q_info['quarter_start'], q_info['quarter_end'])

        for cat in cats:
            expected_combos = repo.get_expected_combos_by_category(cursor, comp_batch_id, cat)
            collected_combos = repo.get_collected_combos_by_category(cursor, event_batch_id, cat)

            missing_combos = expected_combos - collected_combos

            for c_b, c_s in missing_combos:
                results['missing_keywords'].append({
                    'category': cat,
                    'comp_brand': c_b,
                    'comp_sku_name': c_s
                })

            results['summary'][cat] = {
                'total': len(expected_combos),
                'missing': len(missing_combos)
            }

    return results
