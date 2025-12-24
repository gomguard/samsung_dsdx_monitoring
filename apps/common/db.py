"""
데이터베이스 연결 헬퍼
"""

import psycopg2
from config.config import DB_CONFIG, DB_CONFIG_V2


def get_dx_connection():
    """DX PostgreSQL 연결"""
    return psycopg2.connect(
        host=DB_CONFIG['host'],
        port=DB_CONFIG['port'],
        user=DB_CONFIG['user'],
        password=DB_CONFIG['password'],
        database='postgres'
    )


def get_ds_connection():
    """DS MySQL 연결"""
    import pymysql
    return pymysql.connect(
        host=DB_CONFIG_V2['host'],
        port=DB_CONFIG_V2['port'],
        user=DB_CONFIG_V2['user'],
        password=DB_CONFIG_V2['password'],
        database=DB_CONFIG_V2['database'],
        charset='utf8mb4'
    )


def execute_dx_query(query, params=None):
    """DX DB 쿼리 실행 후 결과 반환"""
    conn = get_dx_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(query, params or ())
        columns = [desc[0] for desc in cursor.description] if cursor.description else []
        rows = cursor.fetchall()
        return [dict(zip(columns, row)) for row in rows]
    finally:
        cursor.close()
        conn.close()


def execute_ds_query(query, params=None):
    """DS DB 쿼리 실행 후 결과 반환"""
    conn = get_ds_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(query, params or ())
        columns = [desc[0] for desc in cursor.description] if cursor.description else []
        rows = cursor.fetchall()
        return [dict(zip(columns, row)) for row in rows]
    finally:
        cursor.close()
        conn.close()
