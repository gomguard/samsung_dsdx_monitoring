"""
DX ID 생성 헬퍼
"""

from apps.common.db import DX_SHARE_TOKEN_TABLE


def generate_dx_token_id(cursor):
    """DX 공유 토큰 ID 생성 (token-N)"""
    cursor.execute(f"""
        SELECT COALESCE(MAX(CAST(SUBSTRING(id FROM 7) AS INTEGER)), 0) + 1
        FROM {DX_SHARE_TOKEN_TABLE}
    """)
    next_num = int(cursor.fetchone()[0])

    return f'token-{next_num}'
