"""
Layer 3: 이상치/특수 케이스 검수 (Outlier & Anomaly Detection)
- 비즈니스 로직 위반 및 관련 없는 데이터 검증
- LLM을 이용한 값 검증, '검토 필요' 태그 부착
"""

from django.shortcuts import render
from apps.dx.dx_layer3.api.views import load_timeseries_rules, load_crossfield_rules, load_category_rules


LAYER_CONTEXT = {
    'number': 3,
    'name': '이상치/특수 케이스 검수',
    'name_en': 'Outlier & Anomaly Detection',
    'color': '#d97706',
}

SECTION_TITLES = {
    'dashboard': '대시보드',
    'time_series': '시계열 이상치',
    'cross_field': '크로스 필드 검증',
    'category_spec': '카테고리별 특성',
    'field_missing': '필드 누락',
}


def _get_sidebar_items():
    """사이드바 하위항목 — 규칙 정의에서 이름 목록 추출 (데이터 조회 없음)"""
    sidebar = {}

    # 시계열: DB 규칙의 detail_name
    sidebar['time_series'] = list(dict.fromkeys(
        r['detail_name'] for r in load_timeseries_rules()
    ))

    # 크로스필드: DB 규칙의 section_name (중복 제거)
    sidebar['cross_field'] = list(dict.fromkeys(
        r['section_name'] for r in load_crossfield_rules() if r.get('section_name')
    ))

    # 카테고리별 특성: DB 규칙의 section_name (중복 제거)
    sidebar['category_spec'] = list(dict.fromkeys(
        r['section_name'] for r in load_category_rules() if r.get('section_name')
    ))

    # 필드 누락: 고정
    sidebar['field_missing'] = ['TV', 'HHP']

    return sidebar


def _build_sidebar_groups(section):
    sidebar = _get_sidebar_items()
    return [
        {'key': 'time_series', 'icon': '📈', 'label': '시계열 이상치',
         'expanded': section == 'time_series', 'active': section == 'time_series',
         'items': [{'name': n, 'active': False} for n in sidebar['time_series']]},
        {'key': 'cross_field', 'icon': '🔗', 'label': '크로스 필드 검증',
         'expanded': section == 'cross_field', 'active': section == 'cross_field',
         'items': [{'name': n, 'active': False} for n in sidebar['cross_field']]},
        {'key': 'category_spec', 'icon': '📋', 'label': '카테고리별 특성',
         'expanded': section == 'category_spec', 'active': section == 'category_spec',
         'items': [{'name': n, 'active': False} for n in sidebar['category_spec']]},
        {'key': 'field_missing', 'icon': '🔍', 'label': '필드 누락',
         'expanded': section == 'field_missing', 'active': section == 'field_missing',
         'items': [{'name': n, 'active': False} for n in sidebar['field_missing']]},
    ]


def _build_context(section, request):
    return {
        'layer': LAYER_CONTEXT,
        'section': section,
        'section_title': SECTION_TITLES.get(section, ''),
        'target_date': request.GET.get('date', ''),
        'sidebar_items': _get_sidebar_items(),
        'sidebar_title': 'Layer 3 검증',
        'sidebar_base_url': '/dx/layer3/',
        'sidebar_groups': _build_sidebar_groups(section),
    }


def dashboard(request):
    """Layer 3 대시보드"""
    return render(request, 'layer3/dashboard.html', _build_context('dashboard', request))


def time_series(request):
    """시계열 이상치"""
    return render(request, 'layer3/time_series.html', _build_context('time_series', request))


def cross_field(request):
    """크로스 필드 검증"""
    return render(request, 'layer3/cross_field.html', _build_context('cross_field', request))


def category_spec(request):
    """카테고리별 특성"""
    return render(request, 'layer3/category_spec.html', _build_context('category_spec', request))


def field_missing(request):
    """필드 누락"""
    return render(request, 'layer3/field_missing.html', _build_context('field_missing', request))
