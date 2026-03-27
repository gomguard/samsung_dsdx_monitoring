"""
DX Document Services — DB 쿼리 및 비즈니스 로직
"""

from datetime import datetime, timedelta
from apps.common.db import dx_connection, DX_SHARE_TOKEN_TABLE
from config.config import S3_CONFIG
import uuid
import boto3

SHARE_MAX_AGE = 86400  # 24시간 — dx_document/views.py와 동일 값


def _get_s3_client():
    """S3 클라이언트 생성"""
    return boto3.client(
        's3',
        region_name=S3_CONFIG['region'],
        aws_access_key_id=S3_CONFIG['access_key'],
        aws_secret_access_key=S3_CONFIG['secret_key']
    )


def _delete_s3_objects(files):
    """S3 파일 삭제 (실패 무시)"""
    try:
        s3_client = _get_s3_client()
        for f in files:
            s3_key = f'{f[1]}/{f[0]}'  # file_path/file_name
            s3_client.delete_object(Bucket=S3_CONFIG['bucket'], Key=s3_key)
    except Exception:
        pass


def cleanup_orphan_files(cursor, object_document_id, content, username):
    """content에 없는 에디터 이미지를 soft delete + S3 삭제"""
    if not object_document_id:
        return

    cursor.execute("""
        SELECT file_id, file_name, file_path FROM monitoring_files
        WHERE object_document_id = %s AND is_del = false AND upload_type = 1
    """, (object_document_id,))
    files = cursor.fetchall()

    if not files:
        return

    orphans = [f for f in files if f[1] not in (content or '')]

    if not orphans:
        return

    now = datetime.now()
    orphan_ids = [f[0] for f in orphans]
    cursor.execute("""
        UPDATE monitoring_files SET is_del = true, updated_id = %s, updated_at = %s
        WHERE file_id = ANY(%s)
    """, (username, now, orphan_ids,))

    # S3 삭제 — (file_name, file_path) 형식으로 변환
    _delete_s3_objects([(f[1], f[2]) for f in orphans])


def get_documents_list(category_id):
    """문서 목록 조회 (카테고리별)"""
    with dx_connection() as (conn, cursor):
        cursor.execute("""
            SELECT document_id, category_id, title, created_id,
                   TO_CHAR(updated_at AT TIME ZONE 'Asia/Seoul', 'YYYY-MM-DD HH24:MI') as updated_at
            FROM monitoring_documents
            WHERE category_id = %s AND is_del = false
            ORDER BY created_at DESC
        """, (category_id,))
        columns = [desc[0] for desc in cursor.description]
        documents = [dict(zip(columns, row)) for row in cursor.fetchall()]

    return {'success': True, 'documents': documents, 'total': len(documents)}


def get_document_detail(document_id):
    """문서 상세 조회"""
    with dx_connection() as (conn, cursor):
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

    if not row:
        return None

    return dict(zip(columns, row))


def create_document(category_id, title, content, object_document_id, crawl_date, username):
    """문서 생성 (crawl_date 중복 시 업데이트)"""
    if not object_document_id:
        from apps.common.dx.id_generator import generate_dx_object_document_id
        object_document_id = generate_dx_object_document_id()

    now = datetime.now()
    with dx_connection() as (conn, cursor):
        existing_id = None
        if crawl_date:
            cursor.execute("""
                SELECT document_id FROM monitoring_documents
                WHERE category_id = %s AND crawl_date = %s AND is_del = false
            """, (category_id, crawl_date))
            row = cursor.fetchone()
            if row:
                existing_id = row[0]

        if existing_id:
            cursor.execute("""
                UPDATE monitoring_documents
                SET title = %s, content = %s, updated_id = %s, updated_at = %s
                WHERE document_id = %s
            """, (title, content, username, now, existing_id))
            result_id = existing_id
            result_obj_id = object_document_id or None
            message = '보고서가 업데이트되었습니다.'
        else:
            cursor.execute("""
                INSERT INTO monitoring_documents
                    (category_id, title, content, object_document_id, crawl_date, created_id, created_at, updated_id, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING document_id, object_document_id
            """, (category_id, title, content, object_document_id or None, crawl_date,
                  username, now, username, now))
            result = cursor.fetchone()
            result_id = result[0]
            result_obj_id = result[1]
            message = '문서가 저장되었습니다.'

        cursor.execute("SELECT category_type FROM monitoring_document_categories WHERE category_id = %s", (category_id,))
        cat_row = cursor.fetchone()
        category_type = cat_row[0] if cat_row else 1
        if category_type != 2:
            cleanup_orphan_files(cursor, object_document_id or result_obj_id, content, username)
        conn.commit()

    return {
        'success': True,
        'document_id': result_id,
        'object_document_id': result_obj_id,
        'message': message,
    }


def update_document(document_id, title, content, username):
    """문서 수정"""
    now = datetime.now()
    with dx_connection() as (conn, cursor):
        cursor.execute("""
            SELECT d.object_document_id, COALESCE(c.category_type, 1)
            FROM monitoring_documents d
            LEFT JOIN monitoring_document_categories c ON d.category_id = c.category_id
            WHERE d.document_id = %s AND d.is_del = false
        """, (document_id,))
        row = cursor.fetchone()
        obj_doc_id = row[0] if row else None
        category_type = row[1] if row else 1

        cursor.execute("""
            UPDATE monitoring_documents
            SET title = %s, content = %s, updated_id = %s, updated_at = %s
            WHERE document_id = %s AND is_del = false
        """, (title, content, username, now, document_id))

        if category_type != 2:
            cleanup_orphan_files(cursor, obj_doc_id, content, username)
        conn.commit()

    return {'success': True, 'message': '문서가 수정되었습니다.'}


def delete_document(document_id, username):
    """문서 삭제 (soft delete + 파일 정리)"""
    now = datetime.now()
    files_to_delete = []

    with dx_connection() as (conn, cursor):
        cursor.execute("""
            SELECT object_document_id FROM monitoring_documents
            WHERE document_id = %s
        """, (document_id,))
        row = cursor.fetchone()
        obj_doc_id = row[0] if row else None

        cursor.execute("""
            UPDATE monitoring_documents
            SET is_del = true, updated_id = %s, updated_at = %s
            WHERE document_id = %s
        """, (username, now, document_id))

        if obj_doc_id:
            cursor.execute("""
                SELECT file_name, file_path FROM monitoring_files
                WHERE object_document_id = %s AND is_del = false
            """, (obj_doc_id,))
            files_to_delete = cursor.fetchall()

            cursor.execute("""
                UPDATE monitoring_files SET is_del = true, updated_id = %s, updated_at = %s
                WHERE object_document_id = %s AND is_del = false
            """, (username, now, obj_doc_id))

        conn.commit()

    if files_to_delete:
        _delete_s3_objects(files_to_delete)

    return {'success': True, 'message': '문서가 삭제되었습니다.'}


def upload_file(file, object_document_id, upload_type, username):
    """파일 S3 업로드 + DB 저장"""
    ext = file.name.rsplit('.', 1)[-1].lower() if '.' in file.name else 'png'
    s3_file_name = f'{uuid.uuid4()}.{ext}'

    date_part = object_document_id.split('-')[0]
    year = date_part[:4]
    year_month = date_part[:6]
    s3_path = f'dx-documents/{year}/{year_month}/{object_document_id}'
    s3_key = f'{s3_path}/{s3_file_name}'

    s3_client = _get_s3_client()
    s3_client.upload_fileobj(
        file,
        S3_CONFIG['bucket'],
        s3_key,
        ExtraArgs={'ContentType': file.content_type}
    )

    now = datetime.now()
    with dx_connection() as (conn, cursor):
        cursor.execute("""
            INSERT INTO monitoring_files
                (object_document_id, original_file_name, file_name, file_path,
                 file_size, file_type, upload_type, created_at, created_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING file_id
        """, (object_document_id, file.name, s3_file_name, s3_path,
              file.size, file.content_type, upload_type, now, username))
        file_id = cursor.fetchone()[0]
        conn.commit()

    proxy_url = f'/api/dx/documents/file/{s3_file_name}'
    return {'success': True, 'file_id': file_id, 'url': proxy_url}


def get_file_proxy_url(file_name):
    """파일 프록시 — S3 pre-signed URL 반환 (None이면 파일 없음)"""
    with dx_connection() as (conn, cursor):
        cursor.execute("""
            SELECT file_name, file_path FROM monitoring_files
            WHERE file_name = %s AND is_del = false
        """, (file_name,))
        row = cursor.fetchone()

    if not row:
        return None

    s3_key = f'{row[1]}/{row[0]}'
    s3_client = _get_s3_client()
    url = s3_client.generate_presigned_url(
        'get_object',
        Params={'Bucket': S3_CONFIG['bucket'], 'Key': s3_key},
        ExpiresIn=3600
    )
    return url


def delete_file(file_id, username):
    """첨부파일 개별 삭제 (DB soft delete + S3 삭제). None이면 파일 없음"""
    with dx_connection() as (conn, cursor):
        cursor.execute("""
            SELECT file_name, file_path FROM monitoring_files
            WHERE file_id = %s AND is_del = false
        """, (file_id,))
        row = cursor.fetchone()
        if not row:
            return None

        file_info = row

        now = datetime.now()
        cursor.execute("""
            UPDATE monitoring_files SET is_del = true, updated_id = %s, updated_at = %s
            WHERE file_id = %s
        """, (username, now, file_id))
        conn.commit()

    _delete_s3_objects([file_info])
    return {'success': True, 'message': '파일이 삭제되었습니다.'}


def get_document_files(object_document_id):
    """문서 첨부파일 목록 조회"""
    with dx_connection() as (conn, cursor):
        cursor.execute("""
            SELECT file_id, original_file_name, file_name, file_size, file_type,
                   TO_CHAR(created_at AT TIME ZONE 'Asia/Seoul', 'YYYY-MM-DD HH24:MI') as created_at
            FROM monitoring_files
            WHERE object_document_id = %s AND is_del = false AND upload_type = 2
            ORDER BY created_at
        """, (object_document_id,))
        columns = [desc[0] for desc in cursor.description]
        files = [dict(zip(columns, row)) for row in cursor.fetchall()]

    return {'success': True, 'files': files}


def create_share_token(document_id, category_id, memo, username):
    """문서 공유 토큰 생성"""
    from django.core.signing import TimestampSigner

    signer = TimestampSigner(salt='document-share')
    sign_value = f'{category_id}:{document_id}'
    token = signer.sign(sign_value)

    now = datetime.now()
    expires_at = now + timedelta(seconds=SHARE_MAX_AGE)
    with dx_connection() as (conn, cursor):
        from apps.common.dx.id_generator import generate_dx_token_id
        token_id = generate_dx_token_id(cursor)
        cursor.execute(f"""
            INSERT INTO {DX_SHARE_TOKEN_TABLE}
                (id, document_id, category_id, token, memo, created_id, created_at, expires_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (token_id, document_id, category_id, token, memo, username, now, expires_at))
        conn.commit()

    return {'success': True, 'token': token}


def get_share_list(document_id):
    """문서 공유 이력 조회 (최근 20건)"""
    with dx_connection() as (conn, cursor):
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
            FROM {DX_SHARE_TOKEN_TABLE}
            WHERE document_id = %s
            ORDER BY created_at DESC
            LIMIT 20
        """, (document_id,))
        columns = [desc[0] for desc in cursor.description]
        rows = [dict(zip(columns, row)) for row in cursor.fetchall()]

    return {'success': True, 'shares': rows, 'total': len(rows)}


def revoke_share_token(token_id, username):
    """공유 토큰 차단. 0이면 이미 차단되었거나 존재하지 않음"""
    now = datetime.now()
    with dx_connection() as (conn, cursor):
        cursor.execute(f"""
            UPDATE {DX_SHARE_TOKEN_TABLE}
            SET is_revoked = true, revoked_id = %s, revoked_at = %s
            WHERE id = %s AND is_revoked = false
        """, (username, now, token_id))
        updated = cursor.rowcount
        conn.commit()

    return updated
