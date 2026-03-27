"""
DX Document Services — 문서 페이지 렌더링용 DB 조회 로직
"""

from apps.common.db import dx_connection, DX_SHARE_TOKEN_TABLE


def get_categories_with_doc_count():
    """카테고리 목록 + 문서 수 조회 (index 페이지)"""
    with dx_connection() as (conn, cursor):
        cursor.execute("""
            SELECT c.category_id, c.category_name, c.description, c.sort_order, c.category_type,
                   COALESCE(d.doc_count, 0) as doc_count
            FROM monitoring_document_categories c
            LEFT JOIN (
                SELECT category_id, COUNT(*) as doc_count
                FROM monitoring_documents
                WHERE is_del = false
                GROUP BY category_id
            ) d ON c.category_id = d.category_id
            WHERE c.is_del = false AND c.is_active = true
            ORDER BY c.sort_order, c.created_at
        """)
        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]


def get_categories_for_edit():
    """카테고리 목록 조회 (편집 페이지)"""
    with dx_connection() as (conn, cursor):
        cursor.execute("""
            SELECT category_id, category_name, template_content, category_type
            FROM monitoring_document_categories
            WHERE is_del = false AND is_active = true
            ORDER BY sort_order, created_at
        """)
        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]


def is_token_revoked(token):
    """공유 토큰 차단 여부 확인"""
    with dx_connection() as (conn, cursor):
        cursor.execute(f"""
            SELECT is_revoked FROM {DX_SHARE_TOKEN_TABLE}
            WHERE token = %s
        """, [token])
        row = cursor.fetchone()
        return bool(row and row[0])


def get_shared_document(document_id):
    """공유 문서 조회"""
    with dx_connection() as (conn, cursor):
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


def get_shared_file(file_name):
    """공유 파일 경로 조회 → (file_name, file_path) 또는 None"""
    with dx_connection() as (conn, cursor):
        cursor.execute("""
            SELECT file_name, file_path FROM monitoring_files
            WHERE file_name = %s AND is_del = false
        """, (file_name,))
        row = cursor.fetchone()
        if not row:
            return None
        return {'file_name': row[0], 'file_path': row[1]}
