"""
DS Document API
문서 CRUD, 파일 업로드/삭제, 공유 토큰 관리
"""

from django.http import JsonResponse, HttpResponseRedirect
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from apps.common.response import safe_error
from apps.common.db import ds_connection, DS_SHARE_TOKEN_TABLE
from config.config import S3_CONFIG
from datetime import datetime, timedelta
import json
import boto3


# ── 파일 업로드/프록시 ──────────────────────────────────────────

@login_required
@require_POST
def upload(request):
    """DS 문서 이미지 업로드"""
    from apps.common.ds.files import ds_upload_file

    try:
        file = request.FILES.get('file')
        object_document_id = request.POST.get('object_document_id', '').strip()

        if not file:
            return JsonResponse({'success': False, 'error': '파일이 없습니다.'})
        if not object_document_id:
            return JsonResponse({'success': False, 'error': 'object_document_id가 필요합니다.'})

        try:
            upload_type = int(request.POST.get('upload_type', 1))
        except (ValueError, TypeError):
            upload_type = 1
        if upload_type not in (1, 2):
            upload_type = 1
        result = ds_upload_file(file, object_document_id, request.user.username, upload_type=upload_type)

        proxy_url = f'/api/ds/documents/file/{result["file_name"]}'
        return JsonResponse({
            'success': True,
            'file_id': result['file_id'],
            'url': proxy_url
        })
    except Exception as e:
        return safe_error(e, 'upload')


@login_required
def file_proxy(request, file_name):
    """DS 문서 이미지 프록시 - S3 pre-signed URL로 리다이렉트"""
    try:
        with ds_connection() as (conn, cursor):
            cursor.execute("""
                SELECT file_name, file_path FROM ssd_crawl_db.ds_monitoring_document_files
                WHERE file_name = %s AND is_del = 0
            """, (file_name,))
            row = cursor.fetchone()

        if not row:
            return JsonResponse({'success': False, 'error': '파일을 찾을 수 없습니다.'}, status=404)

        s3_key = f'{row[1]}/{row[0]}'

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


# ── 문서 CRUD ──────────────────────────────────────────────────

@login_required
def documents_list(request):
    """DS 문서 목록 조회 API (카테고리별)"""
    category_id = request.GET.get('category_id', '')
    search_field = request.GET.get('search_field', '')
    search_text = request.GET.get('search_text', '')
    date_from = request.GET.get('date_from', '')
    if not category_id:
        return JsonResponse({'success': False, 'error': '카테고리 ID가 필요합니다.'})

    try:
        with ds_connection() as (conn, cursor):
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
            documents = [dict(zip(columns, row)) for row in cursor.fetchall()]

        return JsonResponse({'success': True, 'documents': documents, 'total': len(documents)})
    except Exception as e:
        return safe_error(e, 'db')


@login_required
def document_detail(request):
    """DS 문서 상세 조회 API"""
    document_id = request.GET.get('document_id', '')
    if not document_id:
        return JsonResponse({'success': False, 'error': '문서 ID가 필요합니다.'})

    try:
        with ds_connection() as (conn, cursor):
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

        if not row:
            return JsonResponse({'success': False, 'error': '문서를 찾을 수 없습니다.'})

        document = dict(zip(columns, row))
        return JsonResponse({'success': True, 'document': document})
    except Exception as e:
        return safe_error(e, 'db')


@login_required
@require_POST
def document_create(request):
    """DS 문서 생성 API"""
    from apps.common.ds.id_generator import generate_ds_id
    from apps.common.ds.files import ds_cleanup_orphan_files

    try:
        data = json.loads(request.body)
        category_id = data.get('category_id', '').strip()
        title = data.get('title', '').strip()
        content = data.get('content', '')
        object_document_id = data.get('object_document_id', '').strip()
        crawl_date = data.get('crawl_date', '').strip() or None

        if not category_id:
            return JsonResponse({'success': False, 'error': '카테고리를 선택하세요.'})
        if not title:
            return JsonResponse({'success': False, 'error': '제목을 입력하세요.'})

        now = datetime.now()
        with ds_connection() as (conn, cursor):
            # 수집일자 중복 저장 방지
            if crawl_date:
                cursor.execute("""
                    SELECT COUNT(*) FROM ssd_crawl_db.ds_monitoring_documents
                    WHERE category_id = %s AND crawl_date = %s AND is_del = 0
                """, (category_id, crawl_date))
                if cursor.fetchone()[0] > 0:
                    return JsonResponse({'success': False, 'error': '해당 일자의 보고서는 이미 저장되었습니다.'})

            document_id = generate_ds_id(cursor, 'ssd_crawl_db.ds_monitoring_documents', 'document_id')
            cursor.execute("""
                INSERT INTO ssd_crawl_db.ds_monitoring_documents
                    (document_id, category_id, title, content, object_document_id, crawl_date,
                     created_id, created_at, updated_id, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (document_id, category_id, title, content, object_document_id or None, crawl_date,
                  request.user.username, now, request.user.username, now))

            # 카테고리 타입 조회 (2=파일저장 모드면 고아 파일 정리 건너뜀)
            cursor.execute("""
                SELECT category_type FROM ssd_crawl_db.ds_monitoring_document_categories
                WHERE category_id = %s
            """, (category_id,))
            cat_row = cursor.fetchone()
            category_type = cat_row[0] if cat_row else 1
            if category_type != 2:
                ds_cleanup_orphan_files(cursor, object_document_id, content, request.user.username)
            conn.commit()

        return JsonResponse({
            'success': True,
            'document_id': document_id,
            'object_document_id': object_document_id,
            'message': '문서가 저장되었습니다.'
        })
    except Exception as e:
        return safe_error(e, 'save')


@login_required
@require_POST
def document_update(request, document_id):
    """DS 문서 수정 API"""
    from apps.common.ds.files import ds_cleanup_orphan_files

    try:
        data = json.loads(request.body)
        title = data.get('title', '').strip()
        content = data.get('content', '')

        if not title:
            return JsonResponse({'success': False, 'error': '제목을 입력하세요.'})

        now = datetime.now()
        with ds_connection() as (conn, cursor):
            # object_document_id, category_type 조회
            cursor.execute("""
                SELECT d.object_document_id, COALESCE(c.category_type, 1)
                FROM ssd_crawl_db.ds_monitoring_documents d
                LEFT JOIN ssd_crawl_db.ds_monitoring_document_categories c ON d.category_id = c.category_id
                WHERE d.document_id = %s AND d.is_del = 0
            """, (document_id,))
            row = cursor.fetchone()
            obj_doc_id = row[0] if row else None
            category_type = row[1] if row else 1

            cursor.execute("""
                UPDATE ssd_crawl_db.ds_monitoring_documents
                SET title = %s, content = %s, updated_id = %s, updated_at = %s
                WHERE document_id = %s AND is_del = 0
            """, (title, content, request.user.username, now, document_id))
            # 카테고리 타입 2(파일저장)면 고아 파일 정리 건너뜀
            if category_type != 2:
                ds_cleanup_orphan_files(cursor, obj_doc_id, content, request.user.username)
            conn.commit()

        return JsonResponse({'success': True, 'message': '문서가 수정되었습니다.'})
    except Exception as e:
        return safe_error(e, 'update')


@login_required
@require_POST
def document_delete(request, document_id):
    """DS 문서 삭제 API (soft delete + 파일 정리)"""
    try:
        now = datetime.now()
        with ds_connection() as (conn, cursor):
            # object_document_id 조회
            cursor.execute("""
                SELECT object_document_id FROM ssd_crawl_db.ds_monitoring_documents
                WHERE document_id = %s
            """, (document_id,))
            row = cursor.fetchone()
            obj_doc_id = row[0] if row else None

            # 문서 soft delete
            cursor.execute("""
                UPDATE ssd_crawl_db.ds_monitoring_documents
                SET is_del = 1, updated_id = %s, updated_at = %s
                WHERE document_id = %s
            """, (request.user.username, now, document_id))

            # 연결된 파일 전체 삭제
            files = []
            if obj_doc_id:
                cursor.execute("""
                    SELECT file_name, file_path FROM ssd_crawl_db.ds_monitoring_document_files
                    WHERE object_document_id = %s AND is_del = 0
                """, (obj_doc_id,))
                files = cursor.fetchall()

                cursor.execute("""
                    UPDATE ssd_crawl_db.ds_monitoring_document_files
                    SET is_del = 1, updated_id = %s, updated_at = %s
                    WHERE object_document_id = %s AND is_del = 0
                """, (request.user.username, now, obj_doc_id))

            conn.commit()

        # S3 삭제 (커넥션 반환 후 처리)
        if files:
            try:
                s3_client = boto3.client(
                    's3',
                    region_name=S3_CONFIG['region'],
                    aws_access_key_id=S3_CONFIG['access_key'],
                    aws_secret_access_key=S3_CONFIG['secret_key']
                )
                for f in files:
                    s3_key = f'{f[1]}/{f[0]}'
                    s3_client.delete_object(Bucket=S3_CONFIG['bucket'], Key=s3_key)
            except Exception:
                pass

        return JsonResponse({'success': True, 'message': '문서가 삭제되었습니다.'})
    except Exception as e:
        return safe_error(e, 'delete')


# ── 첨부파일 관리 ──────────────────────────────────────────────

@login_required
def document_files(request):
    """DS 문서 첨부파일 목록 조회 API"""
    object_document_id = request.GET.get('object_document_id', '')
    if not object_document_id:
        return JsonResponse({'success': False, 'error': 'object_document_id가 필요합니다.'})

    try:
        with ds_connection() as (conn, cursor):
            cursor.execute("""
                SELECT file_id, original_file_name, file_name, file_size, file_type,
                       DATE_FORMAT(created_at, '%%Y-%%m-%%d %%H:%%i') as created_at
                FROM ssd_crawl_db.ds_monitoring_document_files
                WHERE object_document_id = %s AND is_del = 0 AND upload_type = 2
                ORDER BY created_at
            """, (object_document_id,))
            columns = [desc[0] for desc in cursor.description]
            files = [dict(zip(columns, row)) for row in cursor.fetchall()]

        return JsonResponse({'success': True, 'files': files})
    except Exception as e:
        return safe_error(e, 'db')


@login_required
@require_POST
def file_delete(request, file_id):
    """DS 첨부파일 개별 삭제 API (DB soft delete + S3 삭제)"""
    try:
        now = datetime.now()
        with ds_connection() as (conn, cursor):
            cursor.execute("""
                SELECT file_name, file_path FROM ssd_crawl_db.ds_monitoring_document_files
                WHERE file_id = %s AND is_del = 0
            """, (file_id,))
            row = cursor.fetchone()
            if not row:
                return JsonResponse({'success': False, 'error': '파일을 찾을 수 없습니다.'})

            # DB soft delete
            cursor.execute("""
                UPDATE ssd_crawl_db.ds_monitoring_document_files
                SET is_del = 1, updated_id = %s, updated_at = %s
                WHERE file_id = %s
            """, (request.user.username, now, file_id))
            conn.commit()

        # S3 삭제 (커넥션 반환 후 처리)
        try:
            s3_key = f'{row[1]}/{row[0]}'
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
        return safe_error(e, 'delete')


# ── 공유 토큰 관리 ─────────────────────────────────────────────

@login_required
@require_POST
def share_token(request):
    """DS 문서 공유 토큰 생성 API (메모 필수, 매번 새 토큰 생성)"""
    from django.core.signing import TimestampSigner
    from apps.common.ds.id_generator import generate_ds_token_id
    from apps.ds_document.views import SHARE_MAX_AGE

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
        with ds_connection() as (conn, cursor):
            token_id = generate_ds_token_id(cursor)
            cursor.execute(f"""
                INSERT INTO {DS_SHARE_TOKEN_TABLE}
                    (id, document_id, category_id, token, memo, created_id, created_at, expires_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (token_id, document_id, category_id, token, memo, request.user.username, now, expires_at))
            conn.commit()

        return JsonResponse({'success': True, 'token': token})
    except Exception as e:
        return safe_error(e, 'save')


@login_required
def share_list(request):
    """DS 문서 공유 이력 조회 API (SQL 기반 상태 판단, 최근 20건)"""
    document_id = request.GET.get('document_id', '')
    if not document_id:
        return JsonResponse({'success': False, 'error': '문서 ID가 필요합니다.'})

    try:
        with ds_connection() as (conn, cursor):
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
                FROM {DS_SHARE_TOKEN_TABLE}
                WHERE document_id = %s
                ORDER BY created_at DESC
                LIMIT 20
            """, (document_id,))
            columns = [desc[0] for desc in cursor.description]
            rows = [dict(zip(columns, row)) for row in cursor.fetchall()]

        return JsonResponse({'success': True, 'shares': rows, 'total': len(rows)})
    except Exception as e:
        return safe_error(e, 'db')


@login_required
@require_POST
def share_revoke(request):
    """DS 공유 토큰 차단 API"""
    try:
        data = json.loads(request.body)
        token_id = data.get('token_id', '')
        if not token_id:
            return JsonResponse({'success': False, 'error': '토큰 ID가 필요합니다.'})

        now = datetime.now()
        with ds_connection() as (conn, cursor):
            cursor.execute(f"""
                UPDATE {DS_SHARE_TOKEN_TABLE}
                SET is_revoked = 1, revoked_id = %s, revoked_at = %s
                WHERE id = %s AND is_revoked = 0
            """, (request.user.username, now, token_id))
            updated = cursor.rowcount
            conn.commit()

        if updated == 0:
            return JsonResponse({'success': False, 'error': '이미 차단되었거나 존재하지 않는 토큰입니다.'})

        return JsonResponse({'success': True, 'message': '공유 링크가 차단되었습니다.'})
    except Exception as e:
        return safe_error(e, 'update')
