"""
Retail 데이터 백업 유틸리티
- TV: tv_retail_com → tv_retail_com_backup_all
- HHP: hhp_retail_com → hhp_retail_com_backup
"""

from apps.common.db import get_dx_connection


def backup_tv_retail():
    """TV retail 데이터 백업 (신규 데이터만 INSERT)"""
    conn = get_dx_connection()
    cursor = conn.cursor()
    try:
        # 백업되지 않은 건수 조회
        cursor.execute("""
            SELECT COUNT(*) FROM tv_retail_com
            WHERE id NOT IN (SELECT id FROM tv_retail_com_backup_all)
        """)
        count = cursor.fetchone()[0]

        if count > 0:
            # 신규 데이터 백업
            cursor.execute("""
                INSERT INTO tv_retail_com_backup_all
                SELECT * FROM tv_retail_com
                WHERE id NOT IN (SELECT id FROM tv_retail_com_backup_all)
            """)
            conn.commit()

        return {'success': True, 'count': count, 'category': 'TV'}
    except Exception as e:
        conn.rollback()
        return {'success': False, 'error': str(e), 'category': 'TV'}
    finally:
        cursor.close()
        conn.close()


def backup_hhp_retail():
    """HHP retail 데이터 백업 (신규 데이터만 INSERT)"""
    conn = get_dx_connection()
    cursor = conn.cursor()
    try:
        # 백업되지 않은 건수 조회
        cursor.execute("""
            SELECT COUNT(*) FROM hhp_retail_com
            WHERE id NOT IN (SELECT id FROM hhp_retail_com_backup)
        """)
        count = cursor.fetchone()[0]

        if count > 0:
            # 신규 데이터 백업
            cursor.execute("""
                INSERT INTO hhp_retail_com_backup
                SELECT * FROM hhp_retail_com
                WHERE id NOT IN (SELECT id FROM hhp_retail_com_backup)
            """)
            conn.commit()

        return {'success': True, 'count': count, 'category': 'HHP'}
    except Exception as e:
        conn.rollback()
        return {'success': False, 'error': str(e), 'category': 'HHP'}
    finally:
        cursor.close()
        conn.close()


def get_backup_count():
    """백업 대상 건수만 조회 (실제 백업 없음)"""
    conn = get_dx_connection()
    cursor = conn.cursor()
    try:
        # TV 건수
        cursor.execute("""
            SELECT COUNT(*) FROM tv_retail_com
            WHERE id NOT IN (SELECT id FROM tv_retail_com_backup_all)
        """)
        tv_count = cursor.fetchone()[0]

        # HHP 건수
        cursor.execute("""
            SELECT COUNT(*) FROM hhp_retail_com
            WHERE id NOT IN (SELECT id FROM hhp_retail_com_backup)
        """)
        hhp_count = cursor.fetchone()[0]

        return {
            'success': True,
            'tv_count': tv_count,
            'hhp_count': hhp_count,
            'total_count': tv_count + hhp_count
        }
    except Exception as e:
        return {'success': False, 'error': str(e)}
    finally:
        cursor.close()
        conn.close()


def backup_all_retail():
    """TV + HHP 전체 백업"""
    tv_result = backup_tv_retail()
    hhp_result = backup_hhp_retail()

    return {
        'success': tv_result['success'] and hhp_result['success'],
        'tv': tv_result,
        'hhp': hhp_result
    }
