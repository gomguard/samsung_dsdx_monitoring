"""
DX Document API
문서 CRUD, 파일 업로드, 공유 토큰 관리
"""

from django.http import JsonResponse, HttpResponseRedirect
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from apps.common.response import safe_error
from apps.common.db import dx_connection, DX_SHARE_TOKEN_TABLE
from config.config import S3_CONFIG
from datetime import datetime, timedelta
import json
import uuid
import boto3
from botocore.exceptions import ClientError


def cleanup_orphan_files(cursor, object_document_id, content, username):
    """content에 없는 에디터 이미지를 soft delete + S3 삭제"""
    if not object_document_id:
        return

    # DB에서 이 문서의 에디터 이미지(upload_type=1)만 조회
    cursor.execute("""
        SELECT file_id, file_name, file_path FROM monitoring_files
        WHERE object_document_id = %s AND is_del = false AND upload_type = 1
    """, (object_document_id,))
    files = cursor.fetchall()

    if not files:
        return

    # content에 포함되지 않은 파일 찾기
    orphans = [f for f in files if f[1] not in (content or '')]

    if not orphans:
        return

    # DB soft delete
    now = datetime.now()
    orphan_ids = [f[0] for f in orphans]
    cursor.execute("""
        UPDATE monitoring_files SET is_del = true, updated_id = %s, updated_at = %s
        WHERE file_id = ANY(%s)
    """, (username, now, orphan_ids,))

    # S3 삭제
    try:
        s3_client = boto3.client(
            's3',
            region_name=S3_CONFIG['region'],
            aws_access_key_id=S3_CONFIG['access_key'],
            aws_secret_access_key=S3_CONFIG['secret_key']
        )
        for f in orphans:
            s3_key = f'{f[2]}/{f[1]}'  # file_path + / + file_name
            s3_client.delete_object(Bucket=S3_CONFIG['bucket'], Key=s3_key)
    except Exception:
        pass  # S3 삭제 실패해도 DB는 이미 처리됨


def documents_list(request):
    """문서 목록 조회 API (카테고리별)"""
    category_id = request.GET.get('category_id', '')

    if not category_id:
        return JsonResponse({'success': False, 'error': '카테고리 ID가 필요합니다.'})

    try:
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

        return JsonResponse({'success': True, 'documents': documents, 'total': len(documents)})
    except Exception as e:
        return safe_error(e, success=False)


def document_detail(request):
    """문서 상세 조회 API"""
    document_id = request.GET.get('document_id', '')

    if not document_id:
        return JsonResponse({'success': False, 'error': '문서 ID가 필요합니다.'})

    try:
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
            return JsonResponse({'success': False, 'error': '문서를 찾을 수 없습니다.'})

        document = dict(zip(columns, row))
        return JsonResponse({'success': True, 'document': document})
    except Exception as e:
        return safe_error(e, success=False)


@login_required
@require_POST
def document_create(request):
    """문서 생성 API"""
    try:
        data = json.loads(request.body)
        category_id = data.get('category_id', '').strip()
        title = data.get('title', '').strip()
        content = data.get('content', '')
        object_document_id = data.get('object_document_id', '').strip()

        if not category_id:
            return JsonResponse({'success': False, 'error': '카테고리를 선택하세요.'})
        if not title:
            return JsonResponse({'success': False, 'error': '제목을 입력하세요.'})

        now = datetime.now()
        with dx_connection() as (conn, cursor):
            cursor.execute("""
                INSERT INTO monitoring_documents
                    (category_id, title, content, object_document_id, created_id, created_at, updated_id, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING document_id, object_document_id
            """, (category_id, title, content, object_document_id or None,
                  request.user.username, now, request.user.username, now))
            result = cursor.fetchone()
            # 카테고리 타입 조회 (2=파일저장 전용이면 고아 파일 정리 건너뜀)
            cursor.execute("SELECT category_type FROM monitoring_document_categories WHERE category_id = %s", (category_id,))
            cat_row = cursor.fetchone()
            category_type = cat_row[0] if cat_row else 1
            if category_type != 2:
                cleanup_orphan_files(cursor, object_document_id, content, request.user.username)
            conn.commit()

        return JsonResponse({
            'success': True,
            'document_id': result[0],
            'object_document_id': result[1],
            'message': '문서가 저장되었습니다.'
        })
    except Exception as e:
        return safe_error(e, success=False)


@login_required
@require_POST
def document_update(request, document_id):
    """문서 수정 API"""
    try:
        data = json.loads(request.body)
        title = data.get('title', '').strip()
        content = data.get('content', '')

        if not title:
            return JsonResponse({'success': False, 'error': '제목을 입력하세요.'})

        now = datetime.now()
        with dx_connection() as (conn, cursor):
            # object_document_id, category_type 조회
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
            """, (title, content, request.user.username, now, document_id))
            # 카테고리 타입 2(파일저장 전용)면 고아 파일 정리 건너뜀
            if category_type != 2:
                cleanup_orphan_files(cursor, obj_doc_id, content, request.user.username)
            conn.commit()

        return JsonResponse({'success': True, 'message': '문서가 수정되었습니다.'})
    except Exception as e:
        return safe_error(e, success=False)


@login_required
@require_POST
def document_delete(request, document_id):
    """문서 삭제 API (soft delete + 파일 정리)"""
    try:
        now = datetime.now()
        files_to_delete = []

        with dx_connection() as (conn, cursor):
            # object_document_id 조회
            cursor.execute("""
                SELECT object_document_id FROM monitoring_documents
                WHERE document_id = %s
            """, (document_id,))
            row = cursor.fetchone()
            obj_doc_id = row[0] if row else None

            # 문서 soft delete
            cursor.execute("""
                UPDATE monitoring_documents
                SET is_del = true, updated_id = %s, updated_at = %s
                WHERE document_id = %s
            """, (request.user.username, now, document_id))

            # 연결된 파일 전체 삭제
            if obj_doc_id:
                cursor.execute("""
                    SELECT file_name, file_path FROM monitoring_files
                    WHERE object_document_id = %s AND is_del = false
                """, (obj_doc_id,))
                files_to_delete = cursor.fetchall()

                cursor.execute("""
                    UPDATE monitoring_files SET is_del = true, updated_id = %s, updated_at = %s
                    WHERE object_document_id = %s AND is_del = false
                """, (request.user.username, now, obj_doc_id))

            conn.commit()

        # S3 삭제 (커넥션 반환 후)
        if files_to_delete:
            try:
                s3_client = boto3.client(
                    's3',
                    region_name=S3_CONFIG['region'],
                    aws_access_key_id=S3_CONFIG['access_key'],
                    aws_secret_access_key=S3_CONFIG['secret_key']
                )
                for f in files_to_delete:
                    s3_key = f'{f[1]}/{f[0]}'
                    s3_client.delete_object(Bucket=S3_CONFIG['bucket'], Key=s3_key)
            except Exception:
                pass

        return JsonResponse({'success': True, 'message': '문서가 삭제되었습니다.'})
    except Exception as e:
        return safe_error(e, success=False)


@login_required
@require_POST
def upload(request):
    """문서 파일 업로드 API (S3)"""
    try:
        file = request.FILES.get('file')
        object_document_id = request.POST.get('object_document_id', '').strip()
        try:
            upload_type = int(request.POST.get('upload_type', 1))
        except (ValueError, TypeError):
            upload_type = 1
        if upload_type not in (1, 2):
            upload_type = 1

        if not file:
            return JsonResponse({'success': False, 'error': '파일이 없습니다.'})
        if not object_document_id:
            return JsonResponse({'success': False, 'error': 'object_document_id가 필요합니다.'})

        # UUID 파일명 생성
        ext = file.name.rsplit('.', 1)[-1].lower() if '.' in file.name else 'png'
        s3_file_name = f'{uuid.uuid4()}.{ext}'
        # 경로와 파일명 분리 저장
        date_part = object_document_id.split('-')[0]  # 20260207
        year = date_part[:4]       # 2026
        year_month = date_part[:6] # 202602
        s3_path = f'dx-documents/{year}/{year_month}/{object_document_id}'
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

        # 파일 테이블에 저장
        now = datetime.now()
        with dx_connection() as (conn, cursor):
            cursor.execute("""
                INSERT INTO monitoring_files
                    (object_document_id, original_file_name, file_name, file_path,
                     file_size, file_type, upload_type, created_at, created_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING file_id
            """, (object_document_id, file.name, s3_file_name, s3_path,
                  file.size, file.content_type, upload_type, now, request.user.username))
            file_id = cursor.fetchone()[0]
            conn.commit()

        # 프록시 URL 반환 (키 노출 없음, 만료 없음)
        proxy_url = f'/api/dx/documents/file/{s3_file_name}'

        return JsonResponse({
            'success': True,
            'file_id': file_id,
            'url': proxy_url
        })
    except ClientError as e:
        return safe_error(e, success=False)
    except Exception as e:
        return safe_error(e, success=False)


@login_required
def file_proxy(request, file_name):
    """문서 이미지 프록시 - S3 pre-signed URL로 리다이렉트"""
    try:
        with dx_connection() as (conn, cursor):
            cursor.execute("""
                SELECT file_name, file_path FROM monitoring_files
                WHERE file_name = %s AND is_del = false
            """, (file_name,))
            row = cursor.fetchone()

        if not row:
            return JsonResponse({'success': False, 'error': '파일을 찾을 수 없습니다.'}, status=404)

        s3_key = f'{row[1]}/{row[0]}'  # file_path/file_name

        s3_client = boto3.client(
            's3',
            region_name=S3_CONFIG['region'],
            aws_access_key_id=S3_CONFIG['access_key'],
            aws_secret_access_key=S3_CONFIG['secret_key']
        )

        url = s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': S3_CONFIG['bucket'], 'Key': s3_key},
            ExpiresIn=3600
        )

        return HttpResponseRedirect(url)
    except Exception as e:
        return safe_error(e, success=False)


@login_required
@require_POST
def file_delete(request, file_id):
    """첨부파일 개별 삭제 API (DB soft delete + S3 삭제)"""
    try:
        file_info = None
        with dx_connection() as (conn, cursor):
            cursor.execute("""
                SELECT file_name, file_path FROM monitoring_files
                WHERE file_id = %s AND is_del = false
            """, (file_id,))
            row = cursor.fetchone()
            if not row:
                return JsonResponse({'success': False, 'error': '파일을 찾을 수 없습니다.'})

            file_info = row

            # DB soft delete
            now = datetime.now()
            cursor.execute("""
                UPDATE monitoring_files SET is_del = true, updated_id = %s, updated_at = %s
                WHERE file_id = %s
            """, (request.user.username, now, file_id))
            conn.commit()

        # S3 삭제 (커넥션 반환 후)
        try:
            s3_key = f'{file_info[1]}/{file_info[0]}'
            s3_client = boto3.client(
                's3',
                region_name=S3_CONFIG['region'],
                aws_access_key_id=S3_CONFIG['access_key'],
                aws_secret_access_key=S3_CONFIG['secret_key']
            )
            s3_client.delete_object(Bucket=S3_CONFIG['bucket'], Key=s3_key)
        except Exception:
            pass

        return JsonResponse({'success': True, 'message': '파일이 삭제되었습니다.'})
    except Exception as e:
        return safe_error(e, success=False)


@login_required
def document_files(request):
    """문서 첨부파일 목록 조회 API"""
    object_document_id = request.GET.get('object_document_id', '')

    if not object_document_id:
        return JsonResponse({'success': False, 'error': 'object_document_id가 필요합니다.'})

    try:
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

        return JsonResponse({'success': True, 'files': files})
    except Exception as e:
        return safe_error(e, success=False)


@login_required
@require_POST
def share_token(request):
    """문서 공유 토큰 생성 API (메모 필수, 매번 새 토큰 생성)"""
    from django.core.signing import TimestampSigner
    from apps.dx.dx_document.views import SHARE_MAX_AGE

    try:
        data = json.loads(request.body)
        document_id = data.get('document_id', '').strip()
        category_id = data.get('category_id', '').strip()
        memo = data.get('memo', '').strip()

        if not document_id:
            return JsonResponse({'success': False, 'error': '문서 ID가 필요합니다.'})
        if not category_id:
            return JsonResponse({'success': False, 'error': '카테고리 ID가 필요합니다.'})
        if not memo:
            return JsonResponse({'success': False, 'error': '공유 대상 메모를 입력하세요.'})

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
            """, (token_id, document_id, category_id, token, memo, request.user.username, now, expires_at))
            conn.commit()

        return JsonResponse({'success': True, 'token': token})
    except Exception as e:
        return safe_error(e, success=False)


@login_required
def share_list(request):
    """문서 공유 이력 조회 API (SQL 기반 상태 판단, 최근 20건)"""
    document_id = request.GET.get('document_id', '')
    if not document_id:
        return JsonResponse({'success': False, 'error': '문서 ID가 필요합니다.'})

    try:
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

        return JsonResponse({'success': True, 'shares': rows, 'total': len(rows)})
    except Exception as e:
        return safe_error(e, success=False)


@login_required
@require_POST
def share_revoke(request):
    """공유 토큰 차단 API"""
    try:
        data = json.loads(request.body)
        token_id = data.get('token_id', '')
        if not token_id:
            return JsonResponse({'success': False, 'error': '토큰 ID가 필요합니다.'})

        now = datetime.now()
        with dx_connection() as (conn, cursor):
            cursor.execute(f"""
                UPDATE {DX_SHARE_TOKEN_TABLE}
                SET is_revoked = true, revoked_id = %s, revoked_at = %s
                WHERE id = %s AND is_revoked = false
            """, (request.user.username, now, token_id))
            updated = cursor.rowcount
            conn.commit()

        if updated == 0:
            return JsonResponse({'success': False, 'error': '이미 차단되었거나 존재하지 않는 토큰입니다.'})

        return JsonResponse({'success': True, 'message': '공유 링크가 차단되었습니다.'})
    except Exception as e:
        return safe_error(e, success=False)
