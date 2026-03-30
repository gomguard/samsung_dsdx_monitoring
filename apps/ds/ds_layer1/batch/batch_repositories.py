"""
DS Layer 1 - Batch 전용 Repository 모듈

이 모듈은 오직 DB 쿼리(SQL) 실행만을 담당합니다.
데이터 검증, 포맷 변경 등 비즈니스 로직은 서비스(services.py)에서 수행합니다.
"""

from apps.common.common_repositories import (
    execute_ds_query_dict,
    execute_ds_insert,
    execute_ds_update_delete,
    execute_ds_scalar
)
from apps.common.db import ds_connection

def get_batches_by_date(target_date):
    """특정 날짜의 배치 목록 전체 조회"""
    query = """
        SELECT id, date, retailer, start_time, memo, created_at
        FROM ssd_crawl_db.ds_collection_batch_log
        WHERE date = %s
        ORDER BY retailer, start_time
    """
    return execute_ds_query_dict(query, (target_date,))


def count_batches_by_date(target_date):
    """특정 날짜에 배치 데이터가 존재하는지 카운트"""
    query = """
        SELECT COUNT(*) 
        FROM ssd_crawl_db.ds_collection_batch_log
        WHERE date = %s
    """
    return execute_ds_scalar(query, (target_date,))


def insert_batches_bulk(batch_data_list):
    """
    여러 배치를 한 번에 생성 (초기화용)
    batch_data_list = [(date, retailer, start_time, memo), ...]
    생성된 개수 반환
    """
    query = """
        INSERT INTO ssd_crawl_db.ds_collection_batch_log
        (date, retailer, start_time, memo)
        VALUES (%s, %s, %s, %s)
    """
    
    # 여러 건을 한 번의 트랜잭션으로 처리하기 위해 직접 커넥션 제어
    with ds_connection() as (conn, cursor):
        cursor.executemany(query, batch_data_list)
        conn.commit()
        return cursor.rowcount


def insert_batch(date_str, retailer, start_time, memo):
    """단일 배치 추가. 새로 생성된 배치의 ID를 반환"""
    query = """
        INSERT INTO ssd_crawl_db.ds_collection_batch_log
        (date, retailer, start_time, memo)
        VALUES (%s, %s, %s, %s)
    """
    return execute_ds_insert(query, (date_str, retailer, start_time, memo))


def update_batch_dynamic(batch_id, updates_dict):
    """
    배치 데이터 동적 업데이트
    updates_dict = {'start_time': '10:00', 'memo': '수정된 메모'}
    """
    if not updates_dict:
        return -1  # 업데이트 할 내용 없음

    set_clauses = []
    params = []
    
    for key, value in updates_dict.items():
        set_clauses.append(f"{key} = %s")
        params.append(value)
        
    params.append(batch_id)
    
    query = f"""
        UPDATE ssd_crawl_db.ds_collection_batch_log
        SET {', '.join(set_clauses)}
        WHERE id = %s
    """
    
    return execute_ds_update_delete(query, params)


def delete_batch(batch_id):
    """배치 삭제"""
    query = """
        DELETE FROM ssd_crawl_db.ds_collection_batch_log
        WHERE id = %s
    """
    return execute_ds_update_delete(query, (batch_id,))
