"""
DX ID 생성 헬퍼
"""

import random
from datetime import datetime

from apps.common.db import DX_SHARE_TOKEN_TABLE


def generate_dx_object_document_id():
    """DX 문서 object_document_id 생성 (YYYYMMDD-HHMMSS.NNNNNNNNNN)"""
    now = datetime.now()
    date_time = now.strftime('%Y%m%d-%H%M%S')
    rand = str(random.randint(0, 9999999999)).zfill(10)

    return f'{date_time}.{rand}'


def generate_dx_token_id(cursor):
    """DX 공유 토큰 ID 생성 (token-N)"""
    cursor.execute(f"""
        SELECT COALESCE(MAX(CAST(SUBSTRING(id FROM 7) AS INTEGER)), 0) + 1
        FROM {DX_SHARE_TOKEN_TABLE}
    """)
    next_num = int(cursor.fetchone()[0])

    return f'token-{next_num}'
