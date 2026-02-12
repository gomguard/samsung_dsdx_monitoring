"""
DS 파일 공통함수 (업로드, 정리)
"""

import uuid
import boto3
from apps.common.db import get_ds_connection
from apps.common.ds.id_generator import generate_ds_id
from config.config import S3_CONFIG
from datetime import datetime


def ds_upload_file(file, object_document_id, username, upload_type=1):
    """DS 파일 업로드 (S3 + DB)

    Args:
        file: Django UploadedFile 객체
        object_document_id: 문서 식별자 (YYYYMMDD-HHMMSS.NNNNNNNNNN)
        username: 업로드한 사용자명
        upload_type: 1=에디터 이미지, 2=첨부파일

    Returns:
        dict: { file_id, file_name, s3_path }
    """
    # UUID 파일명
    ext = file.name.rsplit('.', 1)[-1].lower() if '.' in file.name else 'png'
    s3_file_name = f'{uuid.uuid4()}.{ext}'

    # S3 경로: ds-documents/YYYY/YYYYMM/{object_document_id}/{uuid}.{ext}
    date_part = object_document_id.split('-')[0]
    year = date_part[:4]
    year_month = date_part[:6]
    s3_path = f'ds-documents/{year}/{year_month}/{object_document_id}'
    s3_key = f'{s3_path}/{s3_file_name}'

    # S3 업로드
    s3_client = boto3.client(
        's3',
        region_name=S3_CONFIG['region'],
        aws_access_key_id=S3_CONFIG['access_key'],
        aws_secret_access_key=S3_CONFIG['secret_key']
    )
    s3_client.upload_fileobj(
        file,
        S3_CONFIG['bucket'],
        s3_key,
        ExtraArgs={'ContentType': file.content_type}
    )

    # DB 저장
    now = datetime.now()
    conn = get_ds_connection()
    cursor = conn.cursor()
    file_id = generate_ds_id(cursor, 'ssd_crawl_db.ds_monitoring_document_files', 'file_id')
    cursor.execute("""
        INSERT INTO ssd_crawl_db.ds_monitoring_document_files
            (file_id, object_document_id, original_file_name, file_name, file_path,
             file_size, file_type, upload_type, created_at, created_id)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, (file_id, object_document_id, file.name, s3_file_name, s3_path,
          file.size, file.content_type, upload_type, now, username))
    conn.commit()
    cursor.close()
    conn.close()

    return {
        'file_id': file_id,
        'file_name': s3_file_name,
        's3_path': s3_path,
    }


def ds_cleanup_orphan_files(cursor, object_document_id, content, username):
    """content에 없는 파일을 soft delete + S3 삭제

    Args:
        cursor: DB cursor (호출자가 관리)
        object_document_id: 문서 식별자
        content: 에디터 HTML 내용
        username: 삭제 처리자
    """
    if not object_document_id:
        return

    cursor.execute("""
        SELECT file_id, file_name, file_path FROM ssd_crawl_db.ds_monitoring_document_files
        WHERE object_document_id = %s AND is_del = 0 AND upload_type = 1
    """, (object_document_id,))
    files = cursor.fetchall()

    if not files:
        return

    orphans = [f for f in files if f[1] not in (content or '')]

    if not orphans:
        return

    now = datetime.now()
    orphan_ids = [f[0] for f in orphans]
    placeholders = ','.join(['%s'] * len(orphan_ids))
    cursor.execute(f"""
        UPDATE ssd_crawl_db.ds_monitoring_document_files
        SET is_del = 1, updated_id = %s, updated_at = %s
        WHERE file_id IN ({placeholders})
    """, [username, now] + orphan_ids)

    try:
        s3_client = boto3.client(
            's3',
            region_name=S3_CONFIG['region'],
            aws_access_key_id=S3_CONFIG['access_key'],
            aws_secret_access_key=S3_CONFIG['secret_key']
        )
        for f in orphans:
            s3_key = f'{f[2]}/{f[1]}'
            s3_client.delete_object(Bucket=S3_CONFIG['bucket'], Key=s3_key)
    except Exception:
        pass
