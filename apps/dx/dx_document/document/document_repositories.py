"""
DX Document Repositories: 데이터베이스 I/O 쿼리 전담 계층 (PostgreSQL 기반)
"""

def get_categories_list_db(cursor):
    """카테고리 목록 조회 (문서 건수 미처리)"""
    cursor.execute("""
        SELECT category_id, category_name, description, sort_order, category_type
        FROM monitoring_document_categories
        WHERE is_del = false AND is_active = true
        ORDER BY sort_order, created_at
    """)
    columns = [desc[0] for desc in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def get_categories_for_edit_db(cursor):
    """카테고리 목록 조회 (편집 페이지)"""
    cursor.execute("""
        SELECT category_id, category_name, template_content, category_type
        FROM monitoring_document_categories
        WHERE is_del = false AND is_active = true
        ORDER BY sort_order, created_at
    """)
    columns = [desc[0] for desc in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def get_shared_document_db(cursor, document_id):
    """공유 문서 단건 조회"""
    cursor.execute("""
        SELECT d.document_id, d.title, d.content,
               c.category_name,
               TO_CHAR(d.created_at, 'YYYY-MM-DD HH24:MI') as created_at
        FROM monitoring_documents d
        LEFT JOIN monitoring_document_categories c ON d.category_id = c.category_id
        WHERE d.document_id = %s AND d.is_del = false
    """, [document_id])
    row = cursor.fetchone()
    if not row:
        return None
    columns = ['document_id', 'title', 'content', 'category_name', 'created_at']
    return dict(zip(columns, row))


def get_orphan_files_db(cursor, object_document_id):
    """특정 폼의 남을 이미지 파일 조회"""
    cursor.execute("""
        SELECT file_id, file_name, file_path FROM monitoring_files
        WHERE object_document_id = %s AND is_del = false AND upload_type = 1
    """, (object_document_id,))
    return cursor.fetchall()


def soft_delete_orphan_files_db(cursor, orphan_ids, username, now):
    """orphan 파일 논리 삭제"""
    cursor.execute("""
        UPDATE monitoring_files SET is_del = true, updated_id = %s, updated_at = %s
        WHERE file_id = ANY(%s)
    """, (username, now, orphan_ids))


def get_documents_list_db(cursor, category_id, search_field='', search_text='', date_from='', date_to=''):
    """문서 목록 조회 (카테고리별)"""
    query = """
        SELECT document_id, category_id, title, created_id,
               TO_CHAR(updated_at AT TIME ZONE 'Asia/Seoul', 'YYYY-MM-DD HH24:MI') as updated_at,
               TO_CHAR(created_at AT TIME ZONE 'Asia/Seoul', 'YYYY-MM-DD HH24:MI') as created_at
        FROM monitoring_documents
        WHERE category_id = %s AND is_del = false
    """
    params = [category_id]

    if date_from:
        query += " AND created_at >= %s::timestamp"
        params.append(date_from + " 00:00:00")
        
    if date_to:
        query += " AND created_at <= %s::timestamp"
        params.append(date_to + " 23:59:59")

    if search_text and search_field in ('title', 'document_id', 'created_id'):
        query += f" AND {search_field} ILIKE %s"
        params.append(f"%{search_text}%")

    query += " ORDER BY created_at DESC"

    cursor.execute(query, params)
    columns = [desc[0] for desc in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def get_document_detail_db(cursor, document_id):
    """문서 상세 조회"""
    cursor.execute("""
        SELECT d.document_id, d.category_id, d.title, d.content, d.object_document_id,
               d.created_id, TO_CHAR(d.created_at AT TIME ZONE 'Asia/Seoul', 'YYYY-MM-DD HH24:MI') as created_at,
               d.updated_id, TO_CHAR(d.updated_at AT TIME ZONE 'Asia/Seoul', 'YYYY-MM-DD HH24:MI') as updated_at,
               COALESCE(c.category_type, 1) as category_type
        FROM monitoring_documents d
        LEFT JOIN monitoring_document_categories c ON d.category_id = c.category_id
        WHERE d.document_id = %s AND d.is_del = false
    """, (document_id,))
    columns = [desc[0] for desc in cursor.description]
    row = cursor.fetchone()
    if row:
        return dict(zip(columns, row))
    return None


def get_document_by_crawl_date_db(cursor, category_id, crawl_date):
    """해당 일자 수집 데이터 문서 존재 여부 확인"""
    cursor.execute("""
        SELECT document_id FROM monitoring_documents
        WHERE category_id = %s AND crawl_date = %s AND is_del = false
    """, (category_id, crawl_date))
    row = cursor.fetchone()
    return row[0] if row else None


def update_document_db(cursor, document_id, title, content, username, now):
    """문서 내용 갱신"""
    cursor.execute("""
        UPDATE monitoring_documents
        SET title = %s, content = %s, updated_id = %s, updated_at = %s
        WHERE document_id = %s AND is_del = false
    """, (title, content, username, now, document_id))


def insert_document_db(cursor, category_id, title, content, object_document_id, crawl_date, username, now):
    """신규 문서 삽입"""
    cursor.execute("""
        INSERT INTO monitoring_documents
            (category_id, title, content, object_document_id, crawl_date, created_id, created_at, updated_id, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING document_id, object_document_id
    """, (category_id, title, content, object_document_id or None, crawl_date, username, now, username, now))
    return cursor.fetchone()


def get_category_type_db(cursor, category_id):
    cursor.execute("SELECT category_type FROM monitoring_document_categories WHERE category_id = %s", (category_id,))
    cat_row = cursor.fetchone()
    return cat_row[0] if cat_row else 1


def get_document_object_id_and_type_db(cursor, document_id):
    """문서 번호를 통해 object_id와 카테고리타입 조회 (삭제나 업데이트시 사용)"""
    cursor.execute("""
        SELECT d.object_document_id, COALESCE(c.category_type, 1)
        FROM monitoring_documents d
        LEFT JOIN monitoring_document_categories c ON d.category_id = c.category_id
        WHERE d.document_id = %s AND d.is_del = false
    """, (document_id,))
    return cursor.fetchone()


def get_document_object_id_db(cursor, document_id):
    cursor.execute("""
        SELECT object_document_id FROM monitoring_documents
        WHERE document_id = %s
    """, (document_id,))
    row = cursor.fetchone()
    return row[0] if row else None


def soft_delete_document_db(cursor, document_id, username, now):
    """문서 논리 삭제 (is_del = true)"""
    cursor.execute("""
        UPDATE monitoring_documents
        SET is_del = true, updated_id = %s, updated_at = %s
        WHERE document_id = %s
    """, (username, now, document_id))


def get_files_by_object_id_db(cursor, object_document_id):
    cursor.execute("""
        SELECT file_name, file_path FROM monitoring_files
        WHERE object_document_id = %s AND is_del = false
    """, (object_document_id,))
    return cursor.fetchall()


def soft_delete_files_by_object_id_db(cursor, object_document_id, username, now):
    cursor.execute("""
        UPDATE monitoring_files SET is_del = true, updated_id = %s, updated_at = %s
        WHERE object_document_id = %s AND is_del = false
    """, (username, now, object_document_id))


def insert_file_db(cursor, object_document_id, original_file_name, s3_file_name, s3_path, file_size, file_type, upload_type, username, now):
    cursor.execute("""
        INSERT INTO monitoring_files
            (object_document_id, original_file_name, file_name, file_path,
             file_size, file_type, upload_type, created_at, created_id)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING file_id
    """, (object_document_id, original_file_name, s3_file_name, s3_path, file_size, file_type, upload_type, now, username))
    return cursor.fetchone()[0]


def get_file_info_by_name_db(cursor, file_name):
    """프록시 위한 단일 파일명으로 조회"""
    cursor.execute("""
        SELECT file_name, file_path FROM monitoring_files
        WHERE file_name = %s AND is_del = false
    """, (file_name,))
    row = cursor.fetchone()
    if not row:
        return None
    return {'file_name': row[0], 'file_path': row[1]}


def get_file_info_by_id_db(cursor, file_id):
    """삭제 위한 ID로 파일 조회"""
    cursor.execute("""
        SELECT file_name, file_path FROM monitoring_files
        WHERE file_id = %s AND is_del = false
    """, (file_id,))
    return cursor.fetchone()


def soft_delete_file_by_id_db(cursor, file_id, username, now):
    cursor.execute("""
        UPDATE monitoring_files SET is_del = true, updated_id = %s, updated_at = %s
        WHERE file_id = %s
    """, (username, now, file_id))


def get_document_files_db(cursor, object_document_id):
    cursor.execute("""
        SELECT file_id, original_file_name, file_name, file_size, file_type,
               TO_CHAR(created_at AT TIME ZONE 'Asia/Seoul', 'YYYY-MM-DD HH24:MI') as created_at
        FROM monitoring_files
        WHERE object_document_id = %s AND is_del = false AND upload_type = 2
        ORDER BY created_at
    """, (object_document_id,))
    columns = [desc[0] for desc in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def is_token_revoked_db(cursor, table_name, token):
    cursor.execute(f"""
        SELECT is_revoked FROM {table_name}
        WHERE token = %s
    """, [token])
    row = cursor.fetchone()
    return bool(row and row[0])


def insert_share_token_db(cursor, table_name, token_id, document_id, category_id, token, memo, username, now, expires_at):
    cursor.execute(f"""
        INSERT INTO {table_name}
            (id, document_id, category_id, token, memo, created_id, created_at, expires_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """, (token_id, document_id, category_id, token, memo, username, now, expires_at))


def get_share_list_db(cursor, table_name, document_id):
    cursor.execute(f"""
        SELECT id, token, created_id, memo,
               TO_CHAR(created_at, 'YYYY-MM-DD HH24:MI') as created_at,
               revoked_id,
               TO_CHAR(revoked_at, 'YYYY-MM-DD HH24:MI') as revoked_at,
               CASE
                   WHEN is_revoked THEN 'revoked'
                   WHEN expires_at IS NOT NULL AND expires_at < NOW() THEN 'expired'
                   WHEN expires_at IS NULL AND created_at < NOW() - INTERVAL '1 day' THEN 'expired'
                   ELSE 'active'
               END as status
        FROM {table_name}
        WHERE document_id = %s
        ORDER BY created_at DESC
        LIMIT 20
    """, (document_id,))
    columns = [desc[0] for desc in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def revoke_share_token_db(cursor, table_name, token_id, username, now):
    cursor.execute(f"""
        UPDATE {table_name}
        SET is_revoked = true, revoked_id = %s, revoked_at = %s
        WHERE id = %s AND is_revoked = false
    """, (username, now, token_id))
    return cursor.rowcount
