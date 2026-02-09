"""
메인 대시보드 뷰
5단계 방어 체계 모니터링 시스템의 메인 페이지
"""

from django.shortcuts import render
from django.core.signing import TimestampSigner, SignatureExpired, BadSignature
from django.http import HttpResponse, HttpResponseRedirect, HttpResponseNotFound
from apps.common.db import get_dx_connection

# 문서 공유 토큰 서명 (1일 만료)
SHARE_SIGNER = TimestampSigner(salt='document-share')
SHARE_MAX_AGE = 86400  # 1일


def index(request):
    """메인 페이지 - DS/DX 선택 화면"""
    context = {
        'data_sources': [
            {
                'id': 'dx',
                'name': 'DX Retail',
                'name_en': 'TV/HHP Retail Monitoring',
                'description': '미국 TV/휴대폰 리테일 데이터 모니터링',
                'sub_description': 'Amazon, Bestbuy, Walmart 리테일 데이터',
                'icon': 'tv',
                'color': '#0d9488',
                'url': '/dx/',
                'tables': ['TV Retail', 'HHP Retail', 'YouTube', 'Sentiment', 'Market Share'],
            },
            {
                'id': 'ds',
                'name': 'DS Retail',
                'name_en': 'Global Price Tracking',
                'description': '글로벌 가격 추적 데이터 모니터링',
                'sub_description': '17개국 리테일러 가격 추적 데이터',
                'icon': 'globe',
                'color': '#1a365d',
                'url': '/ds/',
                'tables': ['Amazon', 'Bestbuy', 'Danawa', 'Currys', 'MediaMarkt', 'Fnac', '...'],
            },
        ]
    }
    return render(request, 'main/index.html', context)


def dx_dashboard(request):
    """DX 대시보드 페이지"""
    context = {
        'data_source': {
            'id': 'dx',
            'name': 'DX Retail',
            'name_en': 'TV/HHP Retail Monitoring',
            'color': '#0d9488',
        },
        'layers': [
            {
                'number': 1,
                'name': '기본 통계 검수',
                'name_en': 'Foundational Integrity Check',
                'description': '수집 건수 및 테이블별 데이터 현황 검증',
                'icon': 'server',
                'color': '#1a365d',
                'url': '/dx/layer1/',
            },
            {
                'number': 2,
                'name': '형식/NULL 검수',
                'name_en': 'Format & Null Validation',
                'description': 'NULL 검증, 형식 검증, 이상치 검증',
                'icon': 'cog',
                'color': '#0d9488',
                'url': '/dx/layer2/',
            },
            {
                'number': 3,
                'name': '이상치/특수 케이스 검수',
                'name_en': 'Outlier & Anomaly Detection',
                'description': '비즈니스 로직 위반 및 관련 없는 데이터 검증',
                'icon': 'search',
                'color': '#d97706',
                'url': '/dx/layer3/',
            },
            # Layer 4, 5 - 추후 개발 예정
            # {
            #     'number': 4,
            #     'name': '문맥/의미 검증',
            #     'name_en': 'Context & Meaning Verification',
            #     'description': '데이터 내 문맥 불일치 및 의미적 모순 검증',
            #     'icon': 'brain',
            #     'color': '#7c3aed',
            #     'url': '/dx/layer4/',
            # },
            # {
            #     'number': 5,
            #     'name': '전문가 전수 검수',
            #     'name_en': 'The Human Firewall',
            #     'description': '검토 필요 태그 기반 전문가 최종 승인',
            #     'icon': 'user-check',
            #     'color': '#475569',
            #     'url': '/dx/layer5/',
            # },
        ]
    }
    return render(request, 'main/dx_dashboard.html', context)


def dx_documents(request):
    """DX 문서 페이지"""
    try:
        conn = get_dx_connection()
        cursor = conn.cursor()
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
        cursor.close()
        conn.close()
    except Exception as e:
        categories = []
        print(f"[ERROR] Failed to load document categories: {e}")

    context = {
        'data_source': {
            'id': 'dx',
            'name': 'DX Retail',
            'name_en': 'TV/HHP Retail Monitoring',
            'color': '#0d9488',
        },
        'categories': categories,
    }
    return render(request, 'main/dx_documents.html', context)


def dx_document_edit(request, document_id=None):
    """DX 문서 편집 페이지"""
    selected_category = request.GET.get('category', '')
    template_content = ''

    try:
        conn = get_dx_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT category_id, category_name, template_content, category_type
            FROM monitoring_document_categories
            WHERE is_del = false AND is_active = true
            ORDER BY sort_order, created_at
        """)
        columns = [desc[0] for desc in cursor.description]
        categories = [dict(zip(columns, row)) for row in cursor.fetchall()]
        cursor.close()
        conn.close()
    except Exception as e:
        categories = []
        print(f"[ERROR] Failed to load categories for edit: {e}")

    selected_category_name = ''
    selected_category_type = int(request.GET.get('type', 1))
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
    return render(request, 'main/dx_document_edit.html', context)


def ds_dashboard(request):
    """DS 대시보드 페이지"""
    context = {
        'data_source': {
            'id': 'ds',
            'name': 'DS Retail',
            'name_en': 'Global Price Tracking',
            'color': '#1a365d',
        },
        'layers': [
            {
                'number': 1,
                'name': '기본 통계 검수',
                'name_en': 'Foundational Integrity Check',
                'description': '수집 건수 및 테이블별 데이터 현황 검증',
                'icon': 'server',
                'color': '#1a365d',
                'url': '/ds/layer1/',
            },
            {
                'number': 2,
                'name': '데이터 오류 검수',
                'name_en': 'Data Error Detection',
                'description': 'NULL 검증, 형식 검증, 데이터 오류 탐지',
                'icon': 'cog',
                'color': '#0d9488',
                'url': '/ds/layer2/',
            },
            {
                'number': 3,
                'name': '연속 오류 추적',
                'name_en': 'Recurring Error Tracking',
                'description': '신규 에러 및 반복 에러 추적',
                'icon': 'search',
                'color': '#d97706',
                'url': '/ds/layer3/',
            },
        ]
    }
    return render(request, 'main/ds_dashboard.html', context)


def dx_document_share(request, token):
    """문서 공유 페이지 (로그인 불필요, 1일 만료)"""
    # 토큰 검증
    try:
        signed_value = SHARE_SIGNER.unsign(token, max_age=SHARE_MAX_AGE)
    except SignatureExpired:
        return render(request, 'main/dx_document_share.html', {
            'error': '만료된 링크입니다. 공유 링크는 생성 후 24시간 동안만 유효합니다.',
            'error_type': 'expired',
        })
    except BadSignature:
        return render(request, 'main/dx_document_share.html', {
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
        conn = get_dx_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT is_revoked FROM monitoring_share_tokens
            WHERE token = %s
        """, [token])
        token_row = cursor.fetchone()
        if token_row and token_row[0]:
            cursor.close()
            conn.close()
            return render(request, 'main/dx_document_share.html', {
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
        cursor.close()
        conn.close()

        if not row:
            return render(request, 'main/dx_document_share.html', {
                'error': '문서를 찾을 수 없습니다.',
                'error_type': 'not_found',
            })

        columns = ['document_id', 'title', 'content', 'category_name', 'created_at']
        document = dict(zip(columns, row))

        # 이미지 URL을 공유 전용 프록시로 치환
        if document.get('content'):
            document['content'] = document['content'].replace(
                '/api/dx/documents/file/',
                f'/share/file/{token}/'
            )
    except Exception as e:
        print(f"[ERROR] Failed to load shared document: {e}")
        return render(request, 'main/dx_document_share.html', {
            'error': '문서를 불러오는 중 오류가 발생했습니다.',
            'error_type': 'error',
        })

    return render(request, 'main/dx_document_share.html', {
        'document': document,
    })


def dx_document_share_file(request, token, file_name):
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
        conn = get_dx_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT is_revoked FROM monitoring_share_tokens
            WHERE token = %s
        """, [token])
        token_row = cursor.fetchone()
        cursor.close()
        conn.close()
        if token_row and token_row[0]:
            return HttpResponseNotFound('유효하지 않은 링크입니다.')
    except Exception:
        pass

    # 파일 조회 + S3에서 직접 읽어서 전달
    try:
        conn = get_dx_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT file_name, file_path FROM monitoring_files
            WHERE file_name = %s AND is_del = false
        """, (file_name,))
        row = cursor.fetchone()
        cursor.close()
        conn.close()

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
