from datetime import datetime, timedelta

from apps.common.db import dx_connection
from apps.common.response import log_error
from apps.dx.dx_layer1.common.context import SECTION_TITLES
from apps.common.dx_schedules import get_kst_time_info, get_schedule_kst_info
from . import sentiment_repositories as repo


RETAILERS = ['amazon', 'bestbuy', 'walmart']

ALLOWED_TABLES = {
    'tv_retail_sentiment', 'hhp_retail_sentiment',
    'tv_retail_com', 'hhp_retail_com',
}
ALLOWED_CRAWL_COLS = {'crawl_datetime', 'crawl_strdatetime'}


def _determine_status(rate, target, sentiment_info):
    if sentiment_info['is_pending']:
        return 'PENDING'
    elif target == 0:
        return 'PENDING'
    elif rate >= 100:
        return 'OK'
    elif sentiment_info['is_collecting']:
        return 'ANALYZING'
    elif rate >= 90:
        return 'WARNING'
    else:
        return 'CRITICAL'


def _build_category_stats(cursor, category, target_date, next_day, sentiment_info, sentiment_pending):
    if category == 'TV':
        sentiment_table = 'tv_retail_sentiment'
        com_table = 'tv_retail_com'
        crawl_col = 'crawl_datetime'
    else:
        sentiment_table = 'hhp_retail_sentiment'
        com_table = 'hhp_retail_com'
        crawl_col = 'crawl_strdatetime'

    if sentiment_table not in ALLOWED_TABLES or com_table not in ALLOWED_TABLES:
        raise ValueError(f"허용되지 않은 테이블: {sentiment_table}, {com_table}")
    if crawl_col not in ALLOWED_CRAWL_COLS:
        raise ValueError(f"허용되지 않은 컬럼: {crawl_col}")

    start_time = f'{target_date} 00:00:00'
    end_time = f'{next_day} 00:00:00'
    target_date_str = target_date.strftime('%Y-%m-%d')

    total_target = repo.get_target_total(cursor, category, target_date_str)
    total_analyzed = repo.get_analyzed_total(cursor, sentiment_table, com_table, crawl_col, start_time, end_time)

    target_details = repo.get_target_details(cursor, category, target_date_str)
    analyzed_details = repo.get_analyzed_details(cursor, sentiment_table, com_table, crawl_col, start_time, end_time)

    sentiment_time_slots_info = [
        {
            'period': '오전',
            'us_time': f'{next_day} {sentiment_info["us_start_hour"]:02d}:00',
            'kr_time': sentiment_info['kst_start']['full_display'],
            'kr_time_end': sentiment_info['kst_end']['full_display'],
            'is_dst': sentiment_info['kst_start']['is_dst']
        },
        {
            'period': '오후',
            'us_time': f'{next_day} {sentiment_info["us_start_hour"]:02d}:00',
            'kr_time': sentiment_info['kst_start']['full_display'],
            'kr_time_end': sentiment_info['kst_end']['full_display'],
            'is_dst': sentiment_info['kst_start']['is_dst']
        },
    ]

    time_slots = []
    ok_slots = 0
    active_slots = 0

    for slot_info in sentiment_time_slots_info:
        period = slot_info['period']
        slot_target = 0
        slot_analyzed = 0
        retailers_data = []

        for retailer in RETAILERS:
            key = f"{retailer}_{period}"
            target = target_details.get(key, 0)
            analyzed = analyzed_details.get(key, 0)
            rate = round((analyzed / target * 100), 1) if target > 0 else 0

            status = _determine_status(rate, target, sentiment_info)

            retailers_data.append({
                'name': retailer.capitalize(),
                'target': target,
                'analyzed': analyzed,
                'rate': rate,
                'status': status
            })

            slot_target += target
            slot_analyzed += analyzed

        slot_rate = round((slot_analyzed / slot_target * 100), 1) if slot_target > 0 else 0
        slot_status = _determine_status(slot_rate, slot_target, sentiment_info)

        if slot_target > 0 and not sentiment_pending:
            active_slots += 1
            if slot_status == 'OK':
                ok_slots += 1

        time_slots.append({
            'time': period,
            'us_time': slot_info['us_time'],
            'kr_time': slot_info['kr_time'],
            'kr_time_end': slot_info['kr_time_end'],
            'is_dst': slot_info['is_dst'],
            'target': slot_target,
            'analyzed': slot_analyzed,
            'rate': slot_rate,
            'status': slot_status,
            'retailers': retailers_data
        })

    total_rate = round((total_analyzed / total_target * 100), 1) if total_target > 0 else 0
    total_status = _determine_status(total_rate, total_target, sentiment_info)

    return {
        'name': category,
        'target': total_target,
        'analyzed': total_analyzed,
        'rate': total_rate,
        'status': total_status,
        'time_slots': time_slots
    }


def get_layer1_stats(cursor, target_date, now):
    next_day = target_date + timedelta(days=1)
    sentiment_info = get_schedule_kst_info('sentiment', next_day, now)

    if not sentiment_info:
        kst_start = get_kst_time_info(1, next_day)
        kr_start_hour = kst_start['hour']
        kr_start_date = kst_start['date']
        kr_end_dt = datetime(kr_start_date.year, kr_start_date.month, kr_start_date.day, kr_start_hour, 0, 0) + timedelta(minutes=240)
        sentiment_info = {
            'us_start_hour': 1,
            'collection_duration_min': 240,
            'kst_start': kst_start,
            'kst_end': {'full_display': kr_end_dt.strftime('%Y-%m-%d %H:00')},
            'time_status': None,
            'is_pending': False,
            'is_collecting': False,
            'collection_done': True
        }

    sentiment_pending = sentiment_info['is_pending'] or sentiment_info['is_collecting']

    tv_sentiment_data = _build_category_stats(cursor, 'TV', target_date, next_day, sentiment_info, sentiment_pending)
    hhp_sentiment_data = _build_category_stats(cursor, 'HHP', target_date, next_day, sentiment_info, sentiment_pending)

    total_sentiment_target = tv_sentiment_data['target'] + hhp_sentiment_data['target']
    total_sentiment_analyzed = tv_sentiment_data['analyzed'] + hhp_sentiment_data['analyzed']
    total_sentiment_rate = round((total_sentiment_analyzed / total_sentiment_target * 100), 1) if total_sentiment_target > 0 else 0

    status_priority = {'OK': 0, 'WARNING': 1, 'ANALYZING': 2, 'CRITICAL': 3, 'PENDING': 4}
    if total_sentiment_target == 0:
        total_sentiment_status = 'PENDING'
    elif sentiment_info['is_pending']:
        total_sentiment_status = 'PENDING'
    elif total_sentiment_rate >= 100:
        total_sentiment_status = 'OK'
    elif sentiment_info['is_collecting']:
        total_sentiment_status = 'ANALYZING'
    else:
        tv_priority = status_priority.get(tv_sentiment_data['status'], 0)
        hhp_priority = status_priority.get(hhp_sentiment_data['status'], 0)
        if tv_priority >= hhp_priority:
            total_sentiment_status = tv_sentiment_data['status']
        else:
            total_sentiment_status = hhp_sentiment_data['status']

    sentiment_ok_count = sum(1 for s in [tv_sentiment_data['status'], hhp_sentiment_data['status']] if s == 'OK')

    check = {
        'name': SECTION_TITLES['sentiment'],
        'description': f'{sentiment_ok_count}/2 카테고리 정상',
        'actual': total_sentiment_analyzed,
        'target': total_sentiment_target,
        'rate': total_sentiment_rate,
        'status': total_sentiment_status,
        'check_type': 'sentiment',
        'us_time': f'{next_day} {sentiment_info["us_start_hour"]:02d}:00',
        'kr_time': sentiment_info['kst_start']['full_display'],
        'kr_time_end': sentiment_info['kst_end']['full_display'],
        'is_dst': sentiment_info['kst_start']['is_dst'],
        'categories': [tv_sentiment_data, hhp_sentiment_data]
    }

    return {
        'check': check,
        'failed_items': []
    }


def get_sentiment_stats(target_date):
    next_day = target_date + timedelta(days=1)
    start_time = f'{target_date} 00:00:00'
    end_time = f'{next_day} 00:00:00'
    target_date_str = target_date.strftime('%Y-%m-%d')

    results = {
        'timestamp': datetime.now().isoformat(),
        'target_date': str(target_date),
        'tv': {
            'target': 0, 'analyzed': 0, 'rate': 0, 'status': 'PENDING', 'details': []
        },
        'hhp': {
            'target': 0, 'analyzed': 0, 'rate': 0, 'status': 'PENDING', 'details': []
        }
    }

    with dx_connection() as (conn, cursor):
        tv_target = repo.get_target_total(cursor, 'TV', target_date_str)
        tv_analyzed = repo.get_analyzed_total(cursor, 'tv_retail_sentiment', 'tv_retail_com', 'crawl_datetime', start_time, end_time)
        tv_target_details = repo.get_target_details(cursor, 'TV', target_date_str)
        tv_analyzed_details = repo.get_analyzed_details(cursor, 'tv_retail_sentiment', 'tv_retail_com', 'crawl_datetime', start_time, end_time)

        hhp_target = repo.get_target_total(cursor, 'HHP', target_date_str)
        hhp_analyzed = repo.get_analyzed_total(cursor, 'hhp_retail_sentiment', 'hhp_retail_com', 'crawl_strdatetime', start_time, end_time)
        hhp_target_details = repo.get_target_details(cursor, 'HHP', target_date_str)
        hhp_analyzed_details = repo.get_analyzed_details(cursor, 'hhp_retail_sentiment', 'hhp_retail_com', 'crawl_strdatetime', start_time, end_time)

    tv_details = []
    for retailer in RETAILERS:
        for period in ['오전', '오후']:
            key = f"{retailer}_{period}"
            target = tv_target_details.get(key, 0)
            analyzed = tv_analyzed_details.get(key, 0)
            rate = round((analyzed / target * 100), 1) if target > 0 else 0

            if target == 0:
                status = 'PENDING'
            elif rate >= 100:
                status = 'OK'
            elif rate >= 90:
                status = 'WARNING'
            else:
                status = 'CRITICAL'

            tv_details.append({
                'retailer': retailer.capitalize(),
                'period': period,
                'target': target,
                'analyzed': analyzed,
                'rate': rate,
                'status': status
            })

    tv_rate = round((tv_analyzed / tv_target * 100), 1) if tv_target > 0 else 0
    if tv_target == 0:
        tv_status = 'PENDING'
    elif tv_rate >= 100:
        tv_status = 'OK'
    elif tv_rate >= 90:
        tv_status = 'WARNING'
    else:
        tv_status = 'CRITICAL'

    results['tv'] = {
        'target': tv_target,
        'analyzed': tv_analyzed,
        'rate': tv_rate,
        'status': tv_status,
        'details': tv_details
    }

    hhp_details = []
    for retailer in RETAILERS:
        for period in ['오전', '오후']:
            key = f"{retailer}_{period}"
            target = hhp_target_details.get(key, 0)
            analyzed = hhp_analyzed_details.get(key, 0)
            rate = round((analyzed / target * 100), 1) if target > 0 else 0

            if target == 0:
                status = 'PENDING'
            elif rate >= 100:
                status = 'OK'
            elif rate >= 90:
                status = 'WARNING'
            else:
                status = 'CRITICAL'

            hhp_details.append({
                'retailer': retailer.capitalize(),
                'period': period,
                'target': target,
                'analyzed': analyzed,
                'rate': rate,
                'status': status
            })

    hhp_rate = round((hhp_analyzed / hhp_target * 100), 1) if hhp_target > 0 else 0
    if hhp_target == 0:
        hhp_status = 'PENDING'
    elif hhp_rate >= 100:
        hhp_status = 'OK'
    elif hhp_rate >= 90:
        hhp_status = 'WARNING'
    else:
        hhp_status = 'CRITICAL'

    results['hhp'] = {
        'target': hhp_target,
        'analyzed': hhp_analyzed,
        'rate': hhp_rate,
        'status': hhp_status,
        'details': hhp_details
    }

    return results


def get_sentiment_raw_data(category, retailer, period, target_date):
    next_day = target_date + timedelta(days=1)

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

    with dx_connection() as (conn, cursor):
        columns, rows = repo.get_sentiment_raw_data_list(cursor, category, retailer, start_time, end_time)

    results['columns'] = columns
    results['total_count'] = len(rows)
    results['data'] = rows

    return results
