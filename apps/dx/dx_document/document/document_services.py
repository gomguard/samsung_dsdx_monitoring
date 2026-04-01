"""
DX Document Services — 비즈니스 로직 및 S3 / 토큰 연동
"""

from datetime import datetime, timedelta
import uuid
import boto3
from django.core.signing import TimestampSigner
from apps.common.db import dx_connection, DX_SHARE_TOKEN_TABLE
from config.config import S3_CONFIG
from .document_repositories import *


SHARE_MAX_AGE = 86400  # 24시간


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
            s3_key = f'{f[1]}/{f[0]}'  # file_path / file_name
            s3_client.delete_object(Bucket=S3_CONFIG['bucket'], Key=s3_key)
    except Exception:
        pass


def cleanup_orphan_files(cursor, object_document_id, content, username, now=None):
    """content에 없는 에디터 이미지를 soft delete + S3 삭제"""
    if now is None:
        now = datetime.now()
    if not object_document_id:
        return

    files = get_orphan_files_db(cursor, object_document_id)
    if not files:
        return

    orphans = [f for f in files if f[1] not in (content or '')]
    if not orphans:
        return

    orphan_ids = [f[0] for f in orphans]
    soft_delete_orphan_files_db(cursor, orphan_ids, username, now)
    
    _delete_s3_objects([(f[1], f[2]) for f in orphans])


def get_categories_list():
    """카테고리 목록 조회 (index 페이지)"""
    with dx_connection() as (conn, cursor):
        return get_categories_list_db(cursor)


def get_categories_for_edit():
    """카테고리 목록 조회 (편집 페이지)"""
    with dx_connection() as (conn, cursor):
        return get_categories_for_edit_db(cursor)


def is_token_revoked(token):
    """공유 토큰 차단 여부 확인"""
    with dx_connection() as (conn, cursor):
        return is_token_revoked_db(cursor, DX_SHARE_TOKEN_TABLE, token)


def get_shared_document(document_id):
    """공유 문서 조회"""
    with dx_connection() as (conn, cursor):
        return get_shared_document_db(cursor, document_id)


def get_shared_file(file_name):
    """공유 파일 경로 조회 (Dict 또는 None)"""
    with dx_connection() as (conn, cursor):
        return get_file_info_by_name_db(cursor, file_name)


def get_documents_list(category_id, search_field='', search_text='', date_from='', date_to=''):
    """문서 목록 조회 (카테고리별)"""
    with dx_connection() as (conn, cursor):
        documents = get_documents_list_db(cursor, category_id, search_field, search_text, date_from, date_to)
    return {'success': True, 'documents': documents, 'total': len(documents)}


def get_document_detail(document_id):
    """문서 상세 조회"""
    with dx_connection() as (conn, cursor):
        return get_document_detail_db(cursor, document_id)


def create_document(category_id, title, content, object_document_id, crawl_date, username):
    """문서 생성 (crawl_date 중복 시 업데이트)"""
    if not object_document_id:
        from apps.common.dx.id_generator import generate_dx_object_document_id
        object_document_id = generate_dx_object_document_id()

    now = datetime.now()
    with dx_connection() as (conn, cursor):
        existing_id = None
        if crawl_date:
            existing_id = get_document_by_crawl_date_db(cursor, category_id, crawl_date)

        if existing_id:
            update_document_db(cursor, existing_id, title, content, username, now)
            result_id = existing_id
            result_obj_id = object_document_id or None
            message = '보고서가 업데이트되었습니다.'
        else:
            result_id, result_obj_id = insert_document_db(cursor, category_id, title, content, object_document_id, crawl_date, username, now)
            message = '문서가 저장되었습니다.'

        category_type = get_category_type_db(cursor, category_id)
        if category_type != 2:
            cleanup_orphan_files(cursor, object_document_id or result_obj_id, content, username, now)
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
        row = get_document_object_id_and_type_db(cursor, document_id)
        obj_doc_id = row[0] if row else None
        category_type = row[1] if row else 1

        update_document_db(cursor, document_id, title, content, username, now)

        if category_type != 2:
            cleanup_orphan_files(cursor, obj_doc_id, content, username, now)
        conn.commit()

    return {'success': True, 'message': '문서가 수정되었습니다.'}


def delete_document(document_id, username):
    """문서 삭제 (soft delete + 파일 정리)"""
    now = datetime.now()
    files_to_delete = []

    with dx_connection() as (conn, cursor):
        obj_doc_id = get_document_object_id_db(cursor, document_id)
        soft_delete_document_db(cursor, document_id, username, now)

        if obj_doc_id:
            files_to_delete = get_files_by_object_id_db(cursor, obj_doc_id)
            soft_delete_files_by_object_id_db(cursor, obj_doc_id, username, now)

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
        file_id = insert_file_db(cursor, object_document_id, file.name, s3_file_name, s3_path, file.size, file.content_type, upload_type, username, now)
        conn.commit()

    proxy_url = f'/api/dx/documents/file/{s3_file_name}'
    return {'success': True, 'file_id': file_id, 'url': proxy_url}


def get_file_proxy_url(file_name):
    """파일 프록시 — S3 pre-signed URL 반환 (None이면 파일 없음)"""
    with dx_connection() as (conn, cursor):
        row = get_file_info_by_name_db(cursor, file_name)

    if not row:
        return None

    s3_key = f'{row["file_path"]}/{row["file_name"]}'
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
        file_info = get_file_info_by_id_db(cursor, file_id)
        if not file_info:
            return None

        now = datetime.now()
        soft_delete_file_by_id_db(cursor, file_id, username, now)
        conn.commit()

    _delete_s3_objects([file_info])
    return {'success': True, 'message': '파일이 삭제되었습니다.'}


def get_document_files(object_document_id):
    """문서 첨부파일 목록 조회"""
    with dx_connection() as (conn, cursor):
        files = get_document_files_db(cursor, object_document_id)
    return {'success': True, 'files': files}


def create_share_token(document_id, category_id, memo, username):
    """문서 공유 토큰 생성"""
    signer = TimestampSigner(salt='document-share')
    sign_value = f'{category_id}:{document_id}'
    token = signer.sign(sign_value)

    now = datetime.now()
    expires_at = now + timedelta(seconds=SHARE_MAX_AGE)
    with dx_connection() as (conn, cursor):
        from apps.common.dx.id_generator import generate_dx_token_id
        token_id = generate_dx_token_id(cursor)
        insert_share_token_db(cursor, DX_SHARE_TOKEN_TABLE, token_id, document_id, category_id, token, memo, username, now, expires_at)
        conn.commit()

    return {'success': True, 'token': token}


def get_share_list(document_id):
    """문서 공유 이력 조회 (최근 20건)"""
    with dx_connection() as (conn, cursor):
        rows = get_share_list_db(cursor, DX_SHARE_TOKEN_TABLE, document_id)
    return {'success': True, 'shares': rows, 'total': len(rows)}


def revoke_share_token(token_id, username):
    """공유 토큰 차단. 0이면 이미 차단되었거나 존재하지 않음"""
    now = datetime.now()
    with dx_connection() as (conn, cursor):
        updated = revoke_share_token_db(cursor, DX_SHARE_TOKEN_TABLE, token_id, username, now)
        conn.commit()
    return updated
