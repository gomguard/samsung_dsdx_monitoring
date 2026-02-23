"""
DX Document 뷰
DX 문서 관리 (이슈보고서, 검수 보고서, 검수 매뉴얼 등)
"""

from django.shortcuts import render
from django.core.signing import TimestampSigner, SignatureExpired, BadSignature
from django.http import HttpResponse, HttpResponseNotFound
from apps.common.db import dx_connection, DX_SHARE_TOKEN_TABLE
from apps.common.response import log_error

# 문서 공유 토큰 서명
SHARE_SIGNER = TimestampSigner(salt='document-share')
SHARE_MAX_AGE = 86400  # 24시간


def index(request):
    """DX 문서 페이지"""
    try:
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
            categories = [dict(zip(columns, row)) for row in cursor.fetchall()]
    except Exception as e:
        categories = []
        log_error(e, 'db')

    context = {
        'data_source': {
            'id': 'dx',
            'name': 'DX Retail',
            'name_en': 'TV/HHP Retail Monitoring',
            'color': '#0d9488',
        },
        'categories': categories,
    }
    return render(request, 'dx_document/index.html', context)


def edit(request, document_id=None):
    """DX 문서 편집 페이지"""
    selected_category = request.GET.get('category', '')
    template_content = ''

    try:
        with dx_connection() as (conn, cursor):
            cursor.execute("""
                SELECT category_id, category_name, template_content, category_type
                FROM monitoring_document_categories
                WHERE is_del = false AND is_active = true
                ORDER BY sort_order, created_at
            """)
            columns = [desc[0] for desc in cursor.description]
            categories = [dict(zip(columns, row)) for row in cursor.fetchall()]
    except Exception as e:
        categories = []
        log_error(e, 'db')

    selected_category_name = ''
    try:
        selected_category_type = int(request.GET.get('type', 1))
    except (ValueError, TypeError):
        selected_category_type = 1
    if selected_category:
        for cat in categories:
            if cat['category_id'] == selected_category:
                selected_category_name = cat['category_name']
                template_content = cat.get('template_content') or ''
                selected_category_type = cat.get('category_type') or 1
                break

    context = {
        'data_source': {
            'id': 'dx',
            'name': 'DX Retail',
            'name_en': 'TV/HHP Retail Monitoring',
            'color': '#0d9488',
        },
        'document_id': document_id,
        'is_new': document_id is None,
        'categories': categories,
        'selected_category': selected_category,
        'selected_category_name': selected_category_name,
        'selected_category_type': selected_category_type,
        'template_content': template_content,
    }
    return render(request, 'dx_document/edit.html', context)


def share(request, token):
    """문서 공유 페이지 (로그인 불필요, 1일 만료)"""
    # 토큰 검증
    try:
        signed_value = SHARE_SIGNER.unsign(token, max_age=SHARE_MAX_AGE)
    except SignatureExpired:
        return render(request, 'dx_document/share.html', {
            'error': '만료된 링크입니다. 공유 링크는 생성 후 24시간 동안만 유효합니다.',
            'error_type': 'expired',
        })
    except BadSignature:
        return render(request, 'dx_document/share.html', {
            'error': '유효하지 않은 링크입니다.',
            'error_type': 'invalid',
        })

    # category_id:document_id 분리
    if ':' in signed_value:
        category_id, document_id = signed_value.split(':', 1)
    else:
        # 하위 호환: 기존 토큰은 document_id만 포함
        document_id = signed_value
        category_id = None

    # DB에서 토큰 차단 여부 확인
    try:
        with dx_connection() as (conn, cursor):
            cursor.execute(f"""
                SELECT is_revoked FROM {DX_SHARE_TOKEN_TABLE}
                WHERE token = %s
            """, [token])
            token_row = cursor.fetchone()
            if token_row and token_row[0]:
                return render(request, 'dx_document/share.html', {
                    'error': '공유가 취소된 링크입니다.',
                    'error_type': 'revoked',
                })

            # 문서 조회
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
                return render(request, 'dx_document/share.html', {
                    'error': '문서를 찾을 수 없습니다.',
                    'error_type': 'not_found',
                })

            columns = ['document_id', 'title', 'content', 'category_name', 'created_at']
            document = dict(zip(columns, row))

            # 이미지 URL을 공유 전용 프록시로 치환
            if document.get('content'):
                document['content'] = document['content'].replace(
                    '/api/dx/documents/file/',
                    f'/dx-share/file/{token}/'
                )
    except Exception as e:
        log_error(e, 'db')
        return render(request, 'dx_document/share.html', {
            'error': '문서를 불러오는 중 오류가 발생했습니다.',
            'error_type': 'error',
        })

    return render(request, 'dx_document/share.html', {
        'document': document,
    })


def share_file(request, token, file_name):
    """공유 문서 이미지 프록시 (토큰 검증 후 S3에서 직접 전달)"""
    import mimetypes
    import boto3
    from config.config import S3_CONFIG

    # 토큰 검증 (동일 만료 시간)
    try:
        SHARE_SIGNER.unsign(token, max_age=SHARE_MAX_AGE)
    except (SignatureExpired, BadSignature):
        return HttpResponseNotFound('유효하지 않은 링크입니다.')

    # 토큰 차단 여부 확인
    try:
        with dx_connection() as (conn, cursor):
            cursor.execute(f"""
                SELECT is_revoked FROM {DX_SHARE_TOKEN_TABLE}
                WHERE token = %s
            """, [token])
            token_row = cursor.fetchone()
            if token_row and token_row[0]:
                return HttpResponseNotFound('유효하지 않은 링크입니다.')
    except Exception:
        pass

    # 파일 조회 + S3에서 직접 읽어서 전달
    try:
        with dx_connection() as (conn, cursor):
            cursor.execute("""
                SELECT file_name, file_path FROM monitoring_files
                WHERE file_name = %s AND is_del = false
            """, (file_name,))
            row = cursor.fetchone()

        if not row:
            return HttpResponseNotFound('파일을 찾을 수 없습니다.')

        s3_key = f'{row[1]}/{row[0]}'
        s3_client = boto3.client(
            's3',
            region_name=S3_CONFIG['region'],
            aws_access_key_id=S3_CONFIG['access_key'],
            aws_secret_access_key=S3_CONFIG['secret_key']
        )
        s3_obj = s3_client.get_object(Bucket=S3_CONFIG['bucket'], Key=s3_key)
        file_data = s3_obj['Body'].read()

        content_type = mimetypes.guess_type(file_name)[0] or 'application/octet-stream'
        response = HttpResponse(file_data, content_type=content_type)
        response['Cache-Control'] = 'private, max-age=3600'
        return response
    except Exception:
        return HttpResponseNotFound('파일을 불러올 수 없습니다.')
