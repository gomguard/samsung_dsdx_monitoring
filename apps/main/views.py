"""
메인 대시보드 뷰
5단계 방어 체계 모니터링 시스템의 메인 페이지
"""

from django.shortcuts import render
from apps.common.db import get_dx_connection


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
            SELECT category_id, category_name, description, sort_order, category_type
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
