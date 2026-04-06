"""
DS Document Repositories: 데이터베이스 I/O 쿼리 전담 계층
"""

def get_document_categories_with_count(cursor):
    """카테고리 목록 및 문서 수 조회 (index 뷰용)"""
    cursor.execute("""
        SELECT c.category_id, c.category_name, c.description, c.sort_order, c.category_type,
               COALESCE(d.doc_count, 0) as doc_count
        FROM ssd_crawl_db.ds_monitoring_document_categories c
        LEFT JOIN (
            SELECT category_id, COUNT(*) as doc_count
            FROM ssd_crawl_db.ds_monitoring_documents
            WHERE is_del = 0
            GROUP BY category_id
        ) d ON c.category_id = d.category_id
        WHERE c.is_del = 0 AND c.is_active = 1
        ORDER BY c.sort_order, c.created_at
    """)
    columns = [desc[0] for desc in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def get_document_categories(cursor):
    """카테고리 목록 조회 (edit 뷰용)"""
    cursor.execute("""
        SELECT category_id, category_name, template_content, category_type
        FROM ssd_crawl_db.ds_monitoring_document_categories
        WHERE is_del = 0 AND is_active = 1
        ORDER BY sort_order, created_at
    """)
    columns = [desc[0] for desc in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def get_document_category_info(cursor, document_id):
    """특정 문서의 카테고리 정보 조회"""
    cursor.execute("""
        SELECT d.category_id, c.category_name, c.category_type
        FROM ssd_crawl_db.ds_monitoring_documents d
        JOIN ssd_crawl_db.ds_monitoring_document_categories c
            ON d.category_id = c.category_id
        WHERE d.document_id = %s AND d.is_del = 0
    """, (document_id,))
    return cursor.fetchone()


def get_share_token_revoked(cursor, table_name, token):
    """토큰 차단 여부 확인"""
    cursor.execute(f"""
        SELECT is_revoked FROM {table_name}
        WHERE token = %s
    """, [token])
    return cursor.fetchone()


def get_shared_document_detail(cursor, document_id):
    """공유 문서 단건 조회"""
    cursor.execute("""
        SELECT d.document_id, d.title, d.content,
               c.category_name,
               DATE_FORMAT(d.created_at, '%%Y-%%m-%%d %%H:%%i') as created_at
        FROM ssd_crawl_db.ds_monitoring_documents d
        LEFT JOIN ssd_crawl_db.ds_monitoring_document_categories c ON d.category_id = c.category_id
        WHERE d.document_id = %s AND d.is_del = 0
    """, [document_id])
    return cursor.fetchone()


def get_document_file_info(cursor, file_name):
    """파일 정보 조회 (프록시 용)"""
    cursor.execute("""
        SELECT file_name, file_path FROM ssd_crawl_db.ds_monitoring_document_files
        WHERE file_name = %s AND is_del = 0
    """, (file_name,))
    return cursor.fetchone()


def get_documents_list_data(cursor, category_id, search_field, search_text, date_from):
    """문서 목록 조회"""
    where = 'WHERE category_id = %s AND is_del = 0'
    params = [category_id]
    if search_text and search_field in ('document_id', 'title', 'created_id'):
        where += ' AND ' + search_field + ' LIKE %s'
        params.append('%' + search_text + '%')
    if date_from:
        where += ' AND DATE(created_at) = %s'
        params.append(date_from)

    cursor.execute("""
        SELECT document_id, category_id, title, crawl_date, created_id,
               DATE_FORMAT(created_at, '%%Y-%%m-%%d %%H:%%i') as created_at
        FROM ssd_crawl_db.ds_monitoring_documents
        """ + where + """
        ORDER BY created_at DESC
    """, params)
    columns = [desc[0] for desc in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def get_document_detail_info(cursor, document_id):
    """문서 상세 정보 조회"""
    cursor.execute("""
        SELECT d.document_id, d.category_id, d.title, d.content, d.object_document_id,
               d.created_id, DATE_FORMAT(d.created_at, '%%Y-%%m-%%d %%H:%%i') as created_at,
               d.updated_id, DATE_FORMAT(d.updated_at, '%%Y-%%m-%%d %%H:%%i') as updated_at,
               COALESCE(c.category_type, 1) as category_type
        FROM ssd_crawl_db.ds_monitoring_documents d
        LEFT JOIN ssd_crawl_db.ds_monitoring_document_categories c ON d.category_id = c.category_id
        WHERE d.document_id = %s AND d.is_del = 0
    """, (document_id,))
    columns = [desc[0] for desc in cursor.description]
    row = cursor.fetchone()
    if row:
        return dict(zip(columns, row))
    return None


def get_document_count_by_crawl_date(cursor, category_id, crawl_date):
    """해당 일자 수집 데이터 문서 존재 여부 확인"""
    cursor.execute("""
        SELECT COUNT(*) FROM ssd_crawl_db.ds_monitoring_documents
        WHERE category_id = %s AND crawl_date = %s AND is_del = 0
    """, (category_id, crawl_date))
    return cursor.fetchone()[0]


def get_document_by_crawl_date(cursor, category_id, crawl_date):
    """해당 일자 문서 조회 (document_id, object_document_id 반환)"""
    cursor.execute("""
        SELECT document_id, object_document_id FROM ssd_crawl_db.ds_monitoring_documents
        WHERE category_id = %s AND crawl_date = %s AND is_del = 0
        LIMIT 1
    """, (category_id, crawl_date))
    return cursor.fetchone()


def insert_document_record(cursor, document_id, category_id, title, content, object_document_id, crawl_date, username, now):
    """신규 문서 데이터 저장"""
    cursor.execute("""
        INSERT INTO ssd_crawl_db.ds_monitoring_documents
            (document_id, category_id, title, content, object_document_id, crawl_date,
             created_id, created_at, updated_id, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, (document_id, category_id, title, content, object_document_id or None, crawl_date,
          username, now, username, now))


def get_category_type(cursor, category_id):
    """카테고리 타입 조회"""
    cursor.execute("""
        SELECT category_type FROM ssd_crawl_db.ds_monitoring_document_categories
        WHERE category_id = %s
    """, (category_id,))
    row = cursor.fetchone()
    return row[0] if row else 1


def get_document_object_id_and_category_type(cursor, document_id):
    """문서의 object ID 및 카테고리 타입 반환"""
    cursor.execute("""
        SELECT d.object_document_id, COALESCE(c.category_type, 1)
        FROM ssd_crawl_db.ds_monitoring_documents d
        LEFT JOIN ssd_crawl_db.ds_monitoring_document_categories c ON d.category_id = c.category_id
        WHERE d.document_id = %s AND d.is_del = 0
    """, (document_id,))
    return cursor.fetchone()


def update_document_record(cursor, document_id, title, content, username, now):
    """문서 데이터 갱신"""
    cursor.execute("""
        UPDATE ssd_crawl_db.ds_monitoring_documents
        SET title = %s, content = %s, updated_id = %s, updated_at = %s
        WHERE document_id = %s AND is_del = 0
    """, (title, content, username, now, document_id))


def get_document_object_id(cursor, document_id):
    """문서의 object_document_id 조회"""
    cursor.execute("""
        SELECT object_document_id FROM ssd_crawl_db.ds_monitoring_documents
        WHERE document_id = %s
    """, (document_id,))
    row = cursor.fetchone()
    return row[0] if row else None


def soft_delete_document(cursor, document_id, username, now):
    """문서 논리 삭제 (is_del = 1)"""
    cursor.execute("""
        UPDATE ssd_crawl_db.ds_monitoring_documents
        SET is_del = 1, updated_id = %s, updated_at = %s
        WHERE document_id = %s
    """, (username, now, document_id))


def get_document_files_for_object(cursor, object_document_id):
    """특정 폼의 첨부파일 이름, 경로 조회"""
    cursor.execute("""
        SELECT file_name, file_path FROM ssd_crawl_db.ds_monitoring_document_files
        WHERE object_document_id = %s AND is_del = 0
    """, (object_document_id,))
    return cursor.fetchall()


def soft_delete_document_files(cursor, object_document_id, username, now):
    """문서에 연결된 파일들의 논리 삭제"""
    cursor.execute("""
        UPDATE ssd_crawl_db.ds_monitoring_document_files
        SET is_del = 1, updated_id = %s, updated_at = %s
        WHERE object_document_id = %s AND is_del = 0
    """, (username, now, object_document_id))


def get_document_files_list(cursor, object_document_id):
    """문서 첨부파일 목록 조회 API 용"""
    cursor.execute("""
        SELECT file_id, original_file_name, file_name, file_size, file_type,
               DATE_FORMAT(created_at, '%%Y-%%m-%%d %%H:%%i') as created_at
        FROM ssd_crawl_db.ds_monitoring_document_files
        WHERE object_document_id = %s AND is_del = 0 AND upload_type = 2
        ORDER BY created_at
    """, (object_document_id,))
    columns = [desc[0] for desc in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def get_file_info_by_id(cursor, file_id):
    """개별 파일 아이디로 파일명, 경로 조회"""
    cursor.execute("""
        SELECT file_name, file_path FROM ssd_crawl_db.ds_monitoring_document_files
        WHERE file_id = %s AND is_del = 0
    """, (file_id,))
    return cursor.fetchone()


def soft_delete_file(cursor, file_id, username, now):
    """단일 파일 논리 삭제"""
    cursor.execute("""
        UPDATE ssd_crawl_db.ds_monitoring_document_files
        SET is_del = 1, updated_id = %s, updated_at = %s
        WHERE file_id = %s
    """, (username, now, file_id))


def insert_share_token(cursor, table_name, token_id, document_id, category_id, token, memo, username, now, expires_at):
    """공유 토큰 DB 저장"""
    cursor.execute(f"""
        INSERT INTO {table_name}
            (id, document_id, category_id, token, memo, created_id, created_at, expires_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """, (token_id, document_id, category_id, token, memo, username, now, expires_at))


def get_share_links_history(cursor, table_name, document_id):
    """공유 링크 생성 내역 조회"""
    cursor.execute(f"""
        SELECT id, token, created_id, memo,
               DATE_FORMAT(created_at, '%%Y-%%m-%%d %%H:%%i') as created_at,
               revoked_id,
               DATE_FORMAT(revoked_at, '%%Y-%%m-%%d %%H:%%i') as revoked_at,
               CASE
                   WHEN is_revoked = 1 THEN 'revoked'
                   WHEN expires_at IS NOT NULL AND expires_at < NOW() THEN 'expired'
                   WHEN expires_at IS NULL AND created_at < DATE_SUB(NOW(), INTERVAL 1 DAY) THEN 'expired'
                   ELSE 'active'
               END as status
        FROM {table_name}
        WHERE document_id = %s
        ORDER BY created_at DESC
        LIMIT 20
    """, (document_id,))
    columns = [desc[0] for desc in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def revoke_share_token_record(cursor, table_name, token_id, username, now):
    """토큰 만료 처리 (상태 변경)"""
    cursor.execute(f"""
        UPDATE {table_name}
        SET is_revoked = 1, revoked_id = %s, revoked_at = %s
        WHERE id = %s AND is_revoked = 0
    """, (username, now, token_id))
    return cursor.rowcount
