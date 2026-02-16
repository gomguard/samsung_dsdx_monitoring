"""
데이터베이스 연결 헬퍼
"""

import psycopg2
from django.conf import settings
from config.config import DB_CONFIG, DB_CONFIG_V2

# 공유 토큰 테이블명 (로컬: test_ 접두사)
DX_SHARE_TOKEN_TABLE = 'test_monitoring_share_tokens' if settings.DEBUG else 'monitoring_share_tokens'
DS_SHARE_TOKEN_TABLE = 'ssd_crawl_db.test_ds_monitoring_share_tokens' if settings.DEBUG else 'ssd_crawl_db.ds_monitoring_share_tokens'


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
