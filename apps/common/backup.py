"""
Retail 데이터 백업 유틸리티
- TV: tv_retail_com → tv_retail_com_backup_all
- HHP: hhp_retail_com → hhp_retail_com_backup
"""

from datetime import datetime
from apps.common.db import get_dx_connection
from apps.common.response import log_error


def _insert_backup_log(cursor, product_line, table_name, target_date, count, min_id, max_id, username):
    """백업 로그 기록 (0건이면 기록 안 함)"""
    if count <= 0:
        return
    cursor.execute("""
        INSERT INTO monitoring_backup_log
            (product_line, table_name, target_date, backup_count, min_id, max_id, executed_id, executed_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """, (product_line, table_name, target_date, count, min_id, max_id, username, datetime.now()))


def _date_condition(date_column, target_date):
    """날짜 필터 조건 생성"""
    if target_date:
        return f"AND DATE({date_column}::timestamp) = %s", (target_date,)
    return "", ()


def backup_tv_retail(username='', target_date=None):
    """TV retail 데이터 백업 (신규 데이터만 INSERT)"""
    conn = get_dx_connection()
    cursor = conn.cursor()
    try:
        date_sql, date_params = _date_condition('a.crawl_datetime', target_date)

        cursor.execute(f"""
            SELECT COUNT(*), MIN(a.id), MAX(a.id)
            FROM tv_retail_com a
            LEFT JOIN tv_retail_com_backup_all b ON a.id = b.id
            WHERE b.id IS NULL
            {date_sql}
        """, date_params)
        count, min_id, max_id = cursor.fetchone()

        if count > 0:
            cursor.execute(f"""
                INSERT INTO tv_retail_com_backup_all
                SELECT a.*
                FROM tv_retail_com a
                LEFT JOIN tv_retail_com_backup_all b ON a.id = b.id
                WHERE b.id IS NULL
                {date_sql}
            """, date_params)
            _insert_backup_log(cursor, 'tv', 'tv_retail_com', target_date, count, min_id, max_id, username)
            conn.commit()

        return {'success': True, 'count': count, 'category': 'TV'}
    except Exception as e:
        conn.rollback()
        log_error(e, 'backup')
        return {'success': False, 'error': '백업 중 오류가 발생했습니다.', 'category': 'TV'}
    finally:
        cursor.close()
        conn.close()


def backup_hhp_retail(username='', target_date=None):
    return {'success': True, 'count': 0, 'category': 'HHP', 'excluded': True}

    """HHP retail 데이터 백업 (신규 데이터만 INSERT)"""
    conn = get_dx_connection()
    cursor = conn.cursor()
    try:
        date_sql, date_params = _date_condition('a.crawl_strdatetime', target_date)

        cursor.execute(f"""
            SELECT COUNT(*), MIN(a.id), MAX(a.id)
            FROM hhp_retail_com a
            LEFT JOIN hhp_retail_com_backup b ON a.id = b.id
            WHERE b.id IS NULL
            {date_sql}
        """, date_params)
        count, min_id, max_id = cursor.fetchone()

        if count > 0:
            cursor.execute(f"""
                INSERT INTO hhp_retail_com_backup
                SELECT a.*
                FROM hhp_retail_com a
                LEFT JOIN hhp_retail_com_backup b ON a.id = b.id
                WHERE b.id IS NULL
                {date_sql}
            """, date_params)
            _insert_backup_log(cursor, 'hhp', 'hhp_retail_com', target_date, count, min_id, max_id, username)
            conn.commit()

        return {'success': True, 'count': count, 'category': 'HHP'}
    except Exception as e:
        conn.rollback()
        log_error(e, 'backup')
        return {'success': False, 'error': '백업 중 오류가 발생했습니다.', 'category': 'HHP'}
    finally:
        cursor.close()
        conn.close()


def get_backup_count(target_date=None):
    """백업 대상 건수만 조회 (실제 백업 없음)"""
    conn = get_dx_connection()
    cursor = conn.cursor()
    try:
        tv_date_sql, tv_params = _date_condition('a.crawl_datetime', target_date)
        cursor.execute(f"""
            SELECT COUNT(*)
            FROM tv_retail_com a
            LEFT JOIN tv_retail_com_backup_all b ON a.id = b.id
            WHERE b.id IS NULL
            {tv_date_sql}
        """, tv_params)
        tv_count = cursor.fetchone()[0]

        return {
            'success': True,
            'tv_count': tv_count,
            'hhp_count': 0,
            'total_count': tv_count
        }
    except Exception as e:
        log_error(e, 'backup')
        return {'success': False, 'error': '백업 조회 중 오류가 발생했습니다.'}
    finally:
        cursor.close()
        conn.close()


def get_backup_status(target_date):
    """백업 상태 확인 — 미백업 건수 먼저, >0일 때만 이력 조회"""
    result = get_backup_count(target_date)
    if not result.get('success'):
        return {'success': False, 'error': result.get('error')}

    pending = result.get('total_count', 0)

    # 미백업 0건이면 자동 통과
    if pending == 0:
        return {'success': True, 'pending_count': 0, 'has_backup': True}

    # 미백업 >0건일 때만 이력 조회
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
            'hhp_count': result.get('hhp_count', 0),
        }
    except Exception as e:
        log_error(e, 'backup')
        return {'success': False, 'error': '백업 상태 조회 중 오류가 발생했습니다.'}
    finally:
        cursor.close()
        conn.close()


def backup_all_retail(username='', target_date=None):
    """TV + HHP 전체 백업"""
    tv_result = backup_tv_retail(username, target_date)
    hhp_result = {'success': True, 'count': 0, 'category': 'HHP', 'excluded': True}

    return {
        'success': tv_result['success'] and hhp_result['success'],
        'tv': tv_result,
        'hhp': hhp_result
    }
