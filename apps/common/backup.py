"""
Retail backup utilities.

Each backup table is expected to have the same visible column order as its
source table so INSERT ... SELECT a.* remains compatible.
"""

from datetime import datetime

from apps.common.db import get_dx_connection
from apps.common.response import log_error


RETAIL_BACKUP_TARGETS = {
    'tv': {
        'category': 'TV',
        'source_table': 'tv_retail_com',
        'backup_table': 'tv_retail_com_backup_all',
        'date_column': 'crawl_datetime',
    },
    'ref': {
        'category': 'REF',
        'source_table': 'ref_retail_com',
        'backup_table': 'ref_retail_com_backup_all',
        'date_column': 'crawl_strdatetime',
    },
    'ldy': {
        'category': 'LDY',
        'source_table': 'ldy_retail_com',
        'backup_table': 'ldy_retail_com_backup_all',
        'date_column': 'crawl_strdatetime',
    },
}


def _insert_backup_log(cursor, product_line, table_name, target_date, count, min_id, max_id, username):
    if count <= 0:
        return
    cursor.execute("""
        INSERT INTO monitoring_backup_log
            (product_line, table_name, target_date, backup_count, min_id, max_id, executed_id, executed_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """, (product_line, table_name, target_date, count, min_id, max_id, username, datetime.now()))


def _date_condition(date_column, target_date):
    if target_date:
        return f"AND DATE(a.{date_column}::timestamp) = %s", (target_date,)
    return "", ()


def _get_target_count(cursor, cfg, target_date=None):
    date_sql, date_params = _date_condition(cfg['date_column'], target_date)
    cursor.execute(f"""
        SELECT COUNT(*), MIN(a.id), MAX(a.id)
        FROM {cfg['source_table']} a
        LEFT JOIN {cfg['backup_table']} b ON a.id = b.id
        WHERE b.id IS NULL
        {date_sql}
    """, date_params)
    count, min_id, max_id = cursor.fetchone()
    return count or 0, min_id, max_id


def _backup_retail_target(product_line, username='', target_date=None):
    cfg = RETAIL_BACKUP_TARGETS[product_line]
    conn = get_dx_connection()
    cursor = conn.cursor()
    try:
        count, min_id, max_id = _get_target_count(cursor, cfg, target_date)
        if count > 0:
            date_sql, date_params = _date_condition(cfg['date_column'], target_date)
            cursor.execute(f"""
                INSERT INTO {cfg['backup_table']}
                SELECT a.*
                FROM {cfg['source_table']} a
                LEFT JOIN {cfg['backup_table']} b ON a.id = b.id
                WHERE b.id IS NULL
                {date_sql}
            """, date_params)
            _insert_backup_log(
                cursor,
                product_line,
                cfg['source_table'],
                target_date,
                count,
                min_id,
                max_id,
                username,
            )
            conn.commit()

        return {'success': True, 'count': count, 'category': cfg['category']}
    except Exception as e:
        conn.rollback()
        log_error(e, 'backup')
        return {'success': False, 'error': '백업 중 오류가 발생했습니다.', 'category': cfg['category']}
    finally:
        cursor.close()
        conn.close()


def backup_tv_retail(username='', target_date=None):
    return _backup_retail_target('tv', username, target_date)


def backup_ref_retail(username='', target_date=None):
    return _backup_retail_target('ref', username, target_date)


def backup_ldy_retail(username='', target_date=None):
    return _backup_retail_target('ldy', username, target_date)


def backup_hhp_retail(username='', target_date=None):
    return {'success': True, 'count': 0, 'category': 'HHP', 'excluded': True}


def get_backup_count(target_date=None):
    conn = get_dx_connection()
    cursor = conn.cursor()
    try:
        result = {'success': True, 'hhp_count': 0}
        total = 0
        for product_line, cfg in RETAIL_BACKUP_TARGETS.items():
            count, _, _ = _get_target_count(cursor, cfg, target_date)
            result[f'{product_line}_count'] = count
            total += count
        result['total_count'] = total
        return result
    except Exception as e:
        log_error(e, 'backup')
        return {'success': False, 'error': '백업 조회 중 오류가 발생했습니다.'}
    finally:
        cursor.close()
        conn.close()


def get_backup_status(target_date):
    result = get_backup_count(target_date)
    if not result.get('success'):
        return {'success': False, 'error': result.get('error')}

    pending = result.get('total_count', 0)
    if pending == 0:
        return {
            'success': True,
            'pending_count': 0,
            'has_backup': True,
            'tv_count': result.get('tv_count', 0),
            'ref_count': result.get('ref_count', 0),
            'ldy_count': result.get('ldy_count', 0),
            'hhp_count': 0,
        }

    conn = get_dx_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT COUNT(*) FROM monitoring_backup_log WHERE target_date = %s
        """, (target_date,))
        has_backup = cursor.fetchone()[0] > 0

        return {
            'success': True,
            'has_backup': has_backup,
            'pending_count': pending,
            'tv_count': result.get('tv_count', 0),
            'ref_count': result.get('ref_count', 0),
            'ldy_count': result.get('ldy_count', 0),
            'hhp_count': 0,
        }
    except Exception as e:
        log_error(e, 'backup')
        return {'success': False, 'error': '백업 상태 조회 중 오류가 발생했습니다.'}
    finally:
        cursor.close()
        conn.close()


def backup_all_retail(username='', target_date=None):
    results = {
        'tv': backup_tv_retail(username, target_date),
        'ref': backup_ref_retail(username, target_date),
        'ldy': backup_ldy_retail(username, target_date),
        'hhp': backup_hhp_retail(username, target_date),
    }
    results['success'] = all(r.get('success') for r in results.values() if isinstance(r, dict))
    return results
