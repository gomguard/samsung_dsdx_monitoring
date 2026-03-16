"""
DS Layer 1 — 배치 로그 서비스
DB 쿼리 + 배치 CRUD (순수 비즈니스 로직)
"""

from apps.common.db import ds_connection
from apps.common.targets import load_monitoring_targets_with_local_time, format_time


def get_batches_for_date(target_date):
    """특정 날짜의 배치 목록을 리테일러별로 그룹화하여 반환"""
    batches_by_retailer = {}

    try:
        with ds_connection() as (conn, cursor):
            query = """
                SELECT id, retailer, start_time, memo
                FROM ssd_crawl_db.ds_collection_batch_log
                WHERE date = %s
                ORDER BY retailer, start_time
            """
            cursor.execute(query, (target_date,))
            rows = cursor.fetchall()

            for row in rows:
                retailer = row[1]
                if retailer not in batches_by_retailer:
                    batches_by_retailer[retailer] = []

                batches_by_retailer[retailer].append({
                    'id': row[0],
                    'start_time': format_time(row[2]) if row[2] else '00:00',
                    'memo': row[3]
                })
    except Exception as e:
        print(f"Error loading batches: {e}")

    return batches_by_retailer


def get_batch_list(cursor, target_date):
    """해당 날짜의 배치 로그 목록 조회"""
    query = """
        SELECT id, date, retailer, start_time, memo, created_at
        FROM ssd_crawl_db.ds_collection_batch_log
        WHERE date = %s
        ORDER BY retailer, start_time
    """
    cursor.execute(query, (target_date,))
    rows = cursor.fetchall()

    batches = []
    for row in rows:
        batches.append({
            'id': row[0],
            'date': str(row[1]),
            'retailer': row[2],
            'start_time': format_time(row[3]) if row[3] else None,
            'memo': row[4],
            'created_at': row[5].isoformat() if row[5] else None
        })

    return batches


def init_batches(cursor, conn, target_date):
    """해당 날짜에 기본 배치 생성. 이미 존재하면 0 반환"""
    check_query = """
        SELECT COUNT(*) FROM ssd_crawl_db.ds_collection_batch_log
        WHERE date = %s
    """
    cursor.execute(check_query, (target_date,))
    count = cursor.fetchone()[0]

    if count > 0:
        return 0

    targets = load_monitoring_targets_with_local_time()
    insert_query = """
        INSERT INTO ssd_crawl_db.ds_collection_batch_log
        (date, retailer, start_time, memo)
        VALUES (%s, %s, %s, %s)
    """

    created_count = 0
    for table_name, retailer, region, korea_time, local_time, country, mall_name in targets:
        cursor.execute(insert_query, (target_date, retailer, local_time + ':00', None))
        created_count += 1

    conn.commit()
    return created_count


def create_batch(cursor, conn, date_str, retailer, start_time, memo):
    """배치 로그 추가. 새로 생성된 ID 반환"""
    insert_query = """
        INSERT INTO ssd_crawl_db.ds_collection_batch_log
        (date, retailer, start_time, memo)
        VALUES (%s, %s, %s, %s)
    """
    cursor.execute(insert_query, (date_str, retailer, start_time, memo))
    conn.commit()

    cursor.execute("SELECT LAST_INSERT_ID()")
    return cursor.fetchone()[0]


def update_batch(cursor, conn, batch_id, start_time, memo):
    """배치 로그 수정. 영향받은 행 수 반환"""
    updates = []
    params = []

    if start_time is not None:
        updates.append("start_time = %s")
        params.append(start_time)

    if memo is not None:
        updates.append("memo = %s")
        params.append(memo)

    if not updates:
        return -1  # 수정할 필드 없음

    params.append(batch_id)

    update_query = f"""
        UPDATE ssd_crawl_db.ds_collection_batch_log
        SET {', '.join(updates)}
        WHERE id = %s
    """
    cursor.execute(update_query, params)
    conn.commit()

    return cursor.rowcount


def delete_batch(cursor, conn, batch_id):
    """배치 로그 삭제. 영향받은 행 수 반환"""
    delete_query = """
        DELETE FROM ssd_crawl_db.ds_collection_batch_log
        WHERE id = %s
    """
    cursor.execute(delete_query, (batch_id,))
    conn.commit()

    return cursor.rowcount
