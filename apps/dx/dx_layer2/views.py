"""
Layer 2: 형식/NULL 검수 (Formatting & Null Validation)
- NULL 검증: 필수 필드의 NULL 또는 빈값 검증
- 형식 검증: 데이터 형식 및 패턴 검증
- 이상치 검증: 논리적 오류 및 이상값 탐지
"""

from django.shortcuts import render
from apps.common.retail_columns import get_all_categories


LAYER_CONTEXT = {
    'number': 2,
    'name': '형식/NULL 검수',
    'name_en': 'Formatting & Null Validation',
    'color': '#0d9488',
}

SECTION_TITLES = {
    'dashboard': '대시보드',
    'null_validation': 'NULL 검증',
    'format_validation': '형식 검증',
    'anomaly_validation': '중복 검증',
}

CATEGORY_NAMES = {
    'tv_retail': 'TV Retail',
    'hhp_retail': 'HHP Retail',
    'youtube': 'YouTube',
    'market': 'Market',
}


def _get_sidebar_items():
    """사이드바 하위항목 — 카테고리 목록에서 추출 (데이터 조회 없음)"""
    categories = get_all_categories()
    items = [{'key': c, 'name': CATEGORY_NAMES.get(c, c)} for c in categories]
    return {'null': items, 'format': items, 'anomaly': items}


def _build_sidebar_groups(section, focus=''):
    categories = get_all_categories()

    def make_items(sec):
        return [{'name': CATEGORY_NAMES.get(c, c), 'active': section == sec and CATEGORY_NAMES.get(c, c) == focus} for c in categories]

    return [
        {'key': 'null_validation', 'icon': '🔍', 'label': 'NULL 검증',
         'expanded': section == 'null_validation', 'active': section == 'null_validation', 'items': make_items('null_validation')},
        {'key': 'format_validation', 'icon': '📋', 'label': '형식 검증',
         'expanded': section == 'format_validation', 'active': section == 'format_validation', 'items': make_items('format_validation')},
        {'key': 'anomaly_validation', 'icon': '🔄', 'label': '중복 검증',
         'expanded': section == 'anomaly_validation', 'active': section == 'anomaly_validation', 'items': make_items('anomaly_validation')},
    ]


def _build_context(section, request):
    focus = request.GET.get('focus', '')
    return {
        'layer': LAYER_CONTEXT,
        'section': section,
        'section_title': SECTION_TITLES.get(section, ''),
        'target_date': request.GET.get('date', ''),
        'sidebar_items': _get_sidebar_items(),
        'sidebar_title': 'Layer 2 검증',
        'sidebar_base_url': '/dx/layer2/',
        'sidebar_groups': _build_sidebar_groups(section, focus),
    }


def dashboard(request):
    """Layer 2 대시보드"""
    return render(request, 'layer2/dashboard.html', _build_context('dashboard', request))


def null_validation(request):
    """NULL 검증"""
    return render(request, 'layer2/null_validation.html', _build_context('null_validation', request))


def format_validation(request):
    """형식 검증"""
    return render(request, 'layer2/format_validation.html', _build_context('format_validation', request))


def anomaly_validation(request):
    """중복 검증"""
    return render(request, 'layer2/anomaly_validation.html', _build_context('anomaly_validation', request))
