"""
이메일 발송 설정 — 식별코드 상수 및 수신자 조회
"""

from apps.common.db import get_dx_connection, dx_table


# 이메일 발송 식별코드 (키 → 표시명)
EMAIL_CONFIG_KEYS = {
    'collection_status_receiver': '수집 현황 보고',
}


def get_recipients(config_key):
    """
    특정 식별코드의 활성 수신자 이메일 목록 반환

    Args:
        config_key: 식별코드 (예: 'collection_status_receiver')

    Returns:
        list of str: 이메일 주소 리스트
    """
    table = dx_table('monitoring_email_recipients')
    conn = None
    try:
        conn = get_dx_connection()
        cursor = conn.cursor()
        cursor.execute(f"""
            SELECT email FROM {table}
            WHERE config_key = %s AND is_active = true AND is_del = 0
            ORDER BY id
        """, [config_key])
        emails = [row[0] for row in cursor.fetchall()]
        cursor.close()
        conn.close()
        return emails
    except Exception:
        if conn:
            try:
                conn.close()
            except Exception:
                pass
        return []


def get_recipients_with_name(config_key):
    """특정 식별코드의 활성 수신자 이름+이메일 목록 반환"""
    table = dx_table('monitoring_email_recipients')
    conn = None
    try:
        conn = get_dx_connection()
        cursor = conn.cursor()
        cursor.execute(f"""
            SELECT recipient_name, email FROM {table}
            WHERE config_key = %s AND is_active = true AND is_del = 0
            ORDER BY id
        """, [config_key])
        rows = [{'name': row[0] or '', 'email': row[1]} for row in cursor.fetchall()]
        cursor.close()
        conn.close()
        return rows
    except Exception:
        if conn:
            try:
                conn.close()
            except Exception:
                pass
        return []
