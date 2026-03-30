"""
DS 모니터링 공통 Repository 헬퍼 모듈

이 모듈은 데이터베이스 Connection 열기/닫기, Commit, 
그리고 가져온 결과(Tuple)를 이름이 있는 사전(Dict)으로 변환하는 반복적인 작업을 캡슐화합니다.
"""

from apps.common.db import ds_connection

def execute_ds_query_dict(query, params=None):
    """
    SELECT 쿼리를 실행하고 결과를 리스트-딕셔너리 형태로 반환합니다.
    (예: [{'id': 1, 'name': 'A'}, ...])
    """
    with ds_connection() as (conn, cursor):
        cursor.execute(query, params or ())
        if cursor.description:
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]
        return []

def execute_ds_insert(query, params=None):
    """
    INSERT 쿼리를 실행하고 새로 생성된 PK (LAST_INSERT_ID)를 반환합니다.
    """
    with ds_connection() as (conn, cursor):
        cursor.execute(query, params or ())
        conn.commit()
        cursor.execute("SELECT LAST_INSERT_ID()")
        return cursor.fetchone()[0]

def execute_ds_update_delete(query, params=None):
    """
    UPDATE / DELETE 쿼리를 실행하고 영향받은 행(rowcount) 개수를 반환합니다.
    """
    with ds_connection() as (conn, cursor):
        cursor.execute(query, params or ())
        conn.commit()
        return cursor.rowcount

def execute_ds_scalar(query, params=None):
    """
    단일 값(예: COUNT 등)을 반환하는 쿼리를 실행합니다.
    """
    with ds_connection() as (conn, cursor):
        cursor.execute(query, params or ())
        row = cursor.fetchone()
        return row[0] if row else None
