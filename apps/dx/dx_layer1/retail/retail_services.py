import re
from datetime import datetime, timedelta

from apps.common.db import dx_connection
from apps.common.retail_columns import get_retailer_columns, get_all_retailer_columns
from apps.common.sea_retail import SEA_RETAIL_TABLES
from apps.common.response import log_error
from apps.dx.dx_layer1.common.context import SECTION_TITLES
from apps.common.dx_schedules import get_retail_time_slots, get_kst_time_info, get_schedule_kst_info
from . import retail_repositories as repo


OK_THRESHOLD = 200
DB_CHECK_STATUS = 'DB_CHECK'

ALLOWED_TABLES = {'tv_retail_com', 'ref_retail_com', 'ldy_retail_com'}
ALLOWED_DATE_FIELDS = {'crawl_datetime::timestamp', 'crawl_datetime', 'crawl_strdatetime'}
ALLOWED_RANK_FIELDS = {'promotion_position', 'trend_rank'}


def _get_tv_retail_status(retailer, count):
    if retailer == 'amazon':
        return 'OK' if count > 200 else DB_CHECK_STATUS
    if retailer in ('bestbuy', 'walmart'):
        return 'OK' if count >= 300 else DB_CHECK_STATUS
    return 'OK' if count >= OK_THRESHOLD else DB_CHECK_STATUS


def _get_tv_retail_threshold(retailer):
    if retailer == 'amazon':
        return 200
    if retailer in ('bestbuy', 'walmart'):
        return 300
    return OK_THRESHOLD


def _get_daily_retailers(all_slots):
    """1일 1회 수집 리테일러 판별"""
    retailer_slot_count = {}
    for slot in all_slots:
        for r in slot.get('retailers', []):
            name = r['name'].lower()
            retailer_slot_count[name] = retailer_slot_count.get(name, 0) + 1
    return {name for name, count in retailer_slot_count.items() if count == 1}


def check_retailer_data(rows, category='TV', slot_retailers=None):
    if slot_retailers:
        retailer_names = [r['name'].lower() for r in slot_retailers]
    else:
        retailer_names = ['amazon', 'bestbuy', 'walmart']

    retailer_counts = {r: {'count': 0, 'main': 0, 'bsr': 0, 'extra': 0} for r in retailer_names}

    for row in rows:
        retailer_name = row[0].lower() if row[0] else ''
        count = row[1]
        if retailer_name in retailer_counts:
            retailer_counts[retailer_name] = {
                'count': count,
                'main': row[2] if len(row) > 2 else 0,
                'bsr': row[3] if len(row) > 3 else 0,
                'extra': row[4] if len(row) > 4 else 0
            }

    expected_map = {}
    if slot_retailers:
        for r in slot_retailers:
            expected_map[r['name'].lower()] = r.get('expected_count', 0) or 0

    retailer_details = []
    total_count = 0
    statuses = []

    for retailer in retailer_names:
        data = retailer_counts[retailer]
        count = data['count']
        total_count += count
        retailer_expected = expected_map.get(retailer, 300)
        ok_threshold = _get_tv_retail_threshold(retailer)

        status = _get_tv_retail_status(retailer, count)

        statuses.append(status)

        if category == 'TV':
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
            'expected': retailer_expected,
            'ok_threshold': ok_threshold,
            'status': status,
            'items': items
        })

    if 'CRITICAL' in statuses:
        overall_status = 'CRITICAL'
    elif DB_CHECK_STATUS in statuses:
        overall_status = DB_CHECK_STATUS
    else:
        overall_status = 'OK'

    return retailer_details, total_count, overall_status


def _build_daily_category_data(cursor, product_line, target_date):
    cfg = SEA_RETAIL_TABLES[product_line]
    rows = repo.query_daily_category_counts(
        cursor,
        cfg['table'],
        cfg['date_column'],
        target_date,
        cfg['retailers'],
    )
    row_map = {row[0].lower(): row for row in rows if row and row[0]}

    retailers = []
    total_count = 0
    total_expected = 0
    statuses = []
    failed_items = []

    for retailer in cfg['retailers']:
        row = row_map.get(retailer.lower())
        count = row[1] if row else 0
        main_count = row[2] if row else 0
        bsr_count = row[3] if row else 0
        expected = cfg['expected'][retailer]
        status = 'OK' if count >= expected else DB_CHECK_STATUS

        total_count += count
        total_expected += expected
        statuses.append(status)

        retailers.append({
            'retailer': retailer,
            'count': count,
            'expected': expected,
            'ok_threshold': expected,
            'status': status,
            'items': [
                {'name': 'Main Rank', 'count': main_count},
                {'name': 'BSR Rank', 'count': bsr_count},
            ]
        })

        if status != 'OK':
            failed_items.append({
                'source': f"{product_line.upper()} Retail - {retailer}",
                'error_type': 'DB 직접 확인 후 결과 공유',
                'expected': f">= {expected}",
                'actual': count,
                'timestamp': f"{product_line.upper()} 오전"
            })

    overall_status = DB_CHECK_STATUS if any(status != 'OK' for status in statuses) else 'OK'

    return {
        'name': product_line.upper(),
        'total': total_count,
        'expected': total_expected,
        'status': overall_status,
        'time_slots': [{
            'name': '오전',
            'us_time': '00:00',
            'kr_time': '',
            'is_dst': False,
            'total': total_count,
            'expected': total_expected,
            'status': overall_status,
            'retailers': retailers,
        }]
    }, failed_items


def get_layer1_stats(cursor, target_date, now):
    next_day = target_date + timedelta(days=1)
    failed_items = []

    time_slots = get_retail_time_slots('TV', target_date)
    tv_daily_retailers = _get_daily_retailers(time_slots)

    tv_time_slots = []
    tv_total_count = 0
    tv_slot_statuses = []

    for slot in time_slots:
        slot_retailers = slot.get('retailers', [])
        slot_expected = sum(r.get('expected_count', 0) for r in slot_retailers) if slot_retailers else 0
        rows = repo.query_retail_counts(cursor, 'tv_retail_com', 'crawl_datetime::timestamp', 'promotion_position', slot['start'], slot['end'], tv_daily_retailers)

        if slot['is_pending']:
            slot_display_status = slot['time_status'] if slot['time_status'] else 'PENDING'
            retailer_details, total, _ = check_retailer_data(rows, 'TV', slot_retailers)
            tv_total_count += total
            tv_time_slots.append({
                'name': slot['name'],
                'us_time': slot['us_time'],
                'kr_time': slot['kr_time'],
                'is_dst': slot.get('is_dst', False),
                'total': total,
                'expected': slot_expected,
                'status': slot_display_status,
                'retailers': retailer_details
            })
        else:
            retailer_details, total, slot_status = check_retailer_data(rows, 'TV', slot_retailers)
            tv_total_count += total
            tv_slot_statuses.append(slot_status)

            tv_time_slots.append({
                'name': slot['name'],
                'us_time': slot['us_time'],
                'kr_time': slot['kr_time'],
                'is_dst': slot.get('is_dst', False),
                'total': total,
                'expected': slot_expected,
                'status': slot_status,
                'retailers': retailer_details
            })

            for r in retailer_details:
                if r['status'] != 'OK':
                    error_type = '수집 없음' if r['count'] == 0 else ('DB 직접 확인 후 결과 공유' if r['status'] == DB_CHECK_STATUS else '수집량 부족')
                    failed_items.append({
                        'source': f"TV Retail - {r['retailer']}",
                        'error_type': error_type,
                        'expected': f"> {r['ok_threshold']}" if r['retailer'].lower() == 'amazon' else f">= {r['ok_threshold']}",
                        'actual': r['count'],
                        'timestamp': f"TV {slot['name']}"
                    })

    tv_has_collecting = any(s['status'] == 'COLLECTING' for s in tv_time_slots)
    tv_all_pending = all(s['status'] == 'PENDING' for s in tv_time_slots)

    if 'CRITICAL' in tv_slot_statuses:
        tv_overall_status = 'CRITICAL'
    elif DB_CHECK_STATUS in tv_slot_statuses:
        tv_overall_status = DB_CHECK_STATUS
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

    tv_active_slots = len([s for s in tv_time_slots if s['status'] not in ['PENDING', 'COLLECTING']])
    tv_ok_slots = len([s for s in tv_time_slots if s['status'] == 'OK'])

    tv_retail_data = {
        'name': 'TV',
        'total': tv_total_count,
        'expected': sum(s['expected'] for s in tv_time_slots if s['status'] not in ['PENDING', 'COLLECTING']),
        'status': tv_overall_status,
        'time_slots': tv_time_slots
    }

    retail_categories = [tv_retail_data]
    for product_line in ('ref', 'ldy'):
        category_data, category_failed_items = _build_daily_category_data(cursor, product_line, target_date)
        retail_categories.append(category_data)
        failed_items.extend(category_failed_items)

    total_retail_count = sum(c['total'] for c in retail_categories)
    total_retail_expected = sum(c['expected'] for c in retail_categories)
    category_statuses = [c['status'] for c in retail_categories]
    if 'CRITICAL' in category_statuses:
        total_retail_status = 'CRITICAL'
    elif DB_CHECK_STATUS in category_statuses:
        total_retail_status = DB_CHECK_STATUS
    elif 'WARNING' in category_statuses:
        total_retail_status = 'WARNING'
    elif 'COLLECTING' in category_statuses:
        total_retail_status = 'COLLECTING'
    elif all(s == 'PENDING' for s in category_statuses):
        total_retail_status = 'PENDING'
    else:
        total_retail_status = 'OK'
    retail_ok_count = len([c for c in retail_categories if c['status'] == 'OK'])

    am_kst = get_kst_time_info(0, target_date)
    pm_kst = get_kst_time_info(12, target_date)

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
        'is_dst': am_kst['is_dst']
    }

    check = {
        'name': SECTION_TITLES['retail'],
        'description': f'{retail_ok_count}/{len(retail_categories)} 카테고리 정상',
        'actual': total_retail_count,
        'expected': total_retail_expected,
        'expected_min': total_retail_expected,
        'status': total_retail_status,
        'check_type': 'retail',
        'time_info': retail_time_info,
        'categories': retail_categories
    }

    return {'check': check, 'failed_items': failed_items}


def get_retail_detail(target_date, product_line):
    if product_line == 'tv':
        with dx_connection() as (conn, cursor):
            rows = repo.get_tv_retail_detail_list(cursor, target_date.strftime('%Y-%m-%d'))
    else:
        cfg = SEA_RETAIL_TABLES.get(product_line)
        if not cfg:
            return {
                'date': str(target_date),
                'product_line': product_line.upper(),
                'results': [],
                'total_retailers': 0,
                'total_products': 0
            }
        with dx_connection() as (conn, cursor):
            rows = repo.query_daily_category_counts(
                cursor,
                cfg['table'],
                cfg['date_column'],
                target_date,
                cfg['retailers'],
            )

    results = []
    for row in rows:
        price_count = row[4] if len(row) > 4 else row[1]
        results.append({
            'retailer': row[0],
            'total': row[1],
            'main_count': row[2],
            'bsr_count': row[3],
            'price_count': price_count,
            'completeness': round((price_count / row[1] * 100), 1) if row[1] > 0 else 0
        })

    return {
        'date': str(target_date),
        'product_line': product_line.upper(),
        'results': results,
        'total_retailers': len(results),
        'total_products': sum(r['total'] for r in results)
    }


def _get_daily_retail_summary(target_date, product_line):
    cfg = SEA_RETAIL_TABLES[product_line]
    table_name = cfg['table']
    date_field = cfg['date_column']
    slot_name = '오전'

    if table_name not in ALLOWED_TABLES:
        raise ValueError(f"허용되지 않은 테이블: {table_name}")
    if date_field not in ALLOWED_DATE_FIELDS:
        raise ValueError(f"허용되지 않은 날짜 필드: {date_field}")

    summary_data = []
    null_columns_data = []
    total_check_count = 0
    total_null_count = 0
    column_checks_data = []

    with dx_connection() as (conn, cursor):
        for retailer in cfg['retailers']:
            check_columns = get_retailer_columns(product_line, retailer)
            for col in check_columns:
                if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', col):
                    raise ValueError(f"허용되지 않은 컬럼명: {col}")

            row = repo.query_daily_category_summary_by_retailer(
                cursor,
                table_name,
                date_field,
                target_date,
                retailer,
            )
            main_count = row[0] or 0
            bsr_count = row[1] or 0
            extra_count = row[2] or 0
            total = row[3] or 0

            summary_data.append({
                'retailer': retailer,
                'rows': [{
                    'time_slot': slot_name,
                    'main': main_count,
                    'bsr': bsr_count,
                    'extra': extra_count,
                    'extra_name': '',
                    'total': total
                }],
                'total': total
            })

            if total > 0 and check_columns:
                total_check_count += len(check_columns)
                count_row = repo.get_retail_summary_null_counts(
                    cursor,
                    table_name,
                    date_field,
                    check_columns,
                    str(target_date),
                    str(target_date),
                    retailer,
                    True,
                )

                if count_row:
                    col_counts = {}
                    null_cols = []
                    for col, cnt in zip(check_columns, count_row):
                        col_counts[col] = cnt
                        if cnt == 0:
                            null_cols.append(col)

                    total_null_count += len(null_cols)
                    column_checks_data.append({
                        'retailer': retailer,
                        'check_columns': check_columns,
                        'time_slots': [{
                            'time_slot': slot_name,
                            'total': total,
                            'counts': col_counts
                        }]
                    })

                    if null_cols:
                        null_columns_data.append({
                            'retailer': retailer,
                            'time_slots': [{
                                'time_slot': slot_name,
                                'null_columns': null_cols
                            }]
                        })

    grand_total = sum(r['total'] for r in summary_data)

    return {
        'date': str(target_date),
        'product_line': product_line.upper(),
        'extra_rank_name': '',
        'summary': summary_data,
        'null_columns': null_columns_data,
        'totals': {
            'grand_total': grand_total,
            'am_total': grand_total,
            'pm_total': 0
        },
        'check_stats': {
            'total_checks': total_check_count,
            'null_count': total_null_count
        },
        'column_checks': column_checks_data
    }


def get_retail_summary(target_date, product_line):
    if product_line != 'tv':
        if product_line in SEA_RETAIL_TABLES:
            return _get_daily_retail_summary(target_date, product_line)
        return {
            'date': str(target_date),
            'product_line': product_line.upper(),
            'extra_rank_name': '',
            'summary': [],
            'null_columns': [],
            'totals': {
                'grand_total': 0,
                'am_total': 0,
                'pm_total': 0
            },
            'check_stats': {
                'total_checks': 0,
                'null_count': 0
            },
            'column_checks': []
        }

    next_day = target_date + timedelta(days=1)

    time_slots = [
        {'name': '오전', 'start': f'{target_date} 00:00:00', 'end': f'{target_date} 12:00:00'},
        {'name': '오후', 'start': f'{target_date} 12:00:00', 'end': f'{next_day} 00:00:00'}
    ]

    table_name = 'tv_retail_com'
    date_field = 'crawl_datetime::timestamp'
    extra_rank_field = 'promotion_position'
    extra_rank_name = 'Promotion'

    if table_name not in ALLOWED_TABLES:
        raise ValueError(f"허용되지 않은 테이블: {table_name}")
    if date_field not in ALLOWED_DATE_FIELDS:
        raise ValueError(f"허용되지 않은 날짜 필드: {date_field}")
    if extra_rank_field not in ALLOWED_RANK_FIELDS:
        raise ValueError(f"허용되지 않은 랭크 필드: {extra_rank_field}")

    all_slots = get_retail_time_slots(product_line, target_date)
    retailer_set = set()
    for s in all_slots:
        for r in s.get('retailers', []):
            retailer_set.add(r['name'])
    retailers = sorted(retailer_set) if retailer_set else ['Amazon', 'Bestbuy', 'Walmart']
    daily_retailers = _get_daily_retailers(all_slots)

    summary_data = []
    null_columns_data = []
    total_check_count = 0
    total_null_count = 0
    column_checks_data = []

    with dx_connection() as (conn, cursor):
        for retailer in retailers:
            retailer_rows = []
            retailer_null_cols = []
            retailer_total = 0
            check_columns = get_retailer_columns(product_line, retailer)

            for col in check_columns:
                if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', col):
                    raise ValueError(f"허용되지 않은 컬럼명: {col}")

            retailer_check_slots = []
            is_daily = retailer.lower() in daily_retailers

            for slot in time_slots:
                if is_daily and slot['name'] == '오후':
                    retailer_rows.append({
                        'time_slot': slot['name'],
                        'main': 0, 'bsr': 0, 'extra': 0,
                        'extra_name': extra_rank_name, 'total': 0
                    })
                    continue

                if is_daily:
                    date_only = slot['start'][:10]
                    cursor.execute(f"""
                        SELECT
                            COUNT(CASE WHEN main_rank IS NOT NULL THEN 1 END) as main_count,
                            COUNT(CASE WHEN bsr_rank IS NOT NULL THEN 1 END) as bsr_count,
                            COUNT(CASE WHEN {extra_rank_field} IS NOT NULL THEN 1 END) as extra_count,
                            COUNT(*) as total
                        FROM {table_name}
                        WHERE DATE({date_field}) = %s
                        AND LOWER(account_name) = LOWER(%s)
                    """, (date_only, retailer))
                    row = cursor.fetchone()
                else:
                    row = repo.query_retail_counts_by_retailer(cursor, table_name, date_field, extra_rank_field, slot['start'], slot['end'], retailer)

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

                if total > 0 and check_columns:
                    total_check_count += len(check_columns)
                    count_row = repo.get_retail_summary_null_counts(cursor, table_name, date_field, check_columns, slot['start'], slot['end'], retailer, is_daily)
                    
                    if count_row:
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


def get_retailer_raw_data(category, retailer, period, target_date):
    category_key = category.lower()
    if category_key not in SEA_RETAIL_TABLES or category_key == 'hhp':
        return {
            'category': category,
            'retailer': retailer,
            'period': period,
            'date': str(target_date),
            'columns': [],
            'data': [],
            'error': 'HHP Retail is excluded from monitoring.'
        }

    next_day = target_date + timedelta(days=1)

    if category_key in ('ref', 'ldy'):
        start_time = f'{target_date} 00:00:00'
        end_time = f'{next_day} 00:00:00'
    elif period == '오전':
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
        product_line = category_key
        cfg = SEA_RETAIL_TABLES[product_line]
        db_columns = get_retailer_columns(product_line, retailer)

        columns = ['id'] + [col for col in db_columns if col != 'id']

        date_column = cfg['date_column']
        table_name = cfg['table']

        if table_name not in ALLOWED_TABLES:
            raise ValueError(f"허용되지 않은 테이블: {table_name}")

        retailer_columns = get_all_retailer_columns(product_line)
        all_valid_columns = set()
        for cols in retailer_columns.values():
            all_valid_columns.update(cols)
        all_valid_columns.add('id')
        invalid_cols = [c for c in columns if c not in all_valid_columns]
        if invalid_cols:
            raise ValueError(f"허용되지 않은 컬럼: {invalid_cols}")

        with dx_connection() as (conn, cursor):
            rows = repo.get_retailer_raw_data_list(cursor, table_name, columns, retailer, date_column, start_time, end_time)

        results['columns'] = columns
        results['total_count'] = len(rows)
        results['data'] = rows

    except Exception as e:
        results['error'] = log_error(e)

    return results


def get_retailer_columns_info():
    result = {}
    for product_line in ('tv', 'ref', 'ldy'):
        columns = get_all_retailer_columns(product_line)
        all_columns = sorted(set(col for cols in columns.values() for col in cols))
        result[product_line] = {
            'columns': columns,
            'all_columns': all_columns
        }
    return result
