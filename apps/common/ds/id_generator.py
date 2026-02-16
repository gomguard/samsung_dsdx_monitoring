"""
DS ID 생성 헬퍼
"""

import random
from datetime import datetime, timezone, timedelta
from apps.common.db import DS_SHARE_TOKEN_TABLE

KST = timezone(timedelta(hours=9))


def generate_ds_id(cursor, table, column):
    """DS 문서 시스템용 날짜 기반 ID 생성 (YYYYMMDD-NNNN)"""
    kst_now = datetime.now(timezone.utc).astimezone(KST)
    today_prefix = kst_now.strftime('%Y%m%d')

    cursor.execute(f"""
        SELECT COALESCE(MAX(CAST(SUBSTRING({column}, 10) AS UNSIGNED)), 0) + 1
        FROM {table}
        WHERE {column} LIKE %s
    """, (f'{today_prefix}-%',))
    next_num = int(cursor.fetchone()[0])

    return f'{today_prefix}-{next_num:04d}'


def generate_ds_object_document_id():
    """DS 문서 object_document_id 생성 (YYYYMMDD-HHMMSS.NNNNNNNNNN)"""
    kst_now = datetime.now(timezone.utc).astimezone(KST)
    date_time = kst_now.strftime('%Y%m%d-%H%M%S')
    rand = str(random.randint(0, 9999999999)).zfill(10)

    return f'{date_time}.{rand}'


def generate_ds_token_id(cursor):
    """DS 공유 토큰 ID 생성 (token-N)"""
    cursor.execute(f"""
        SELECT COALESCE(MAX(CAST(SUBSTRING(id, 7) AS UNSIGNED)), 0) + 1
        FROM {DS_SHARE_TOKEN_TABLE}
    """)
    next_num = int(cursor.fetchone()[0])

    return f'token-{next_num}'
