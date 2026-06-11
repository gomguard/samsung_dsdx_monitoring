"""
Layer 3 공통 컨텍스트 빌더 — 사이드바, 레이아웃 등
"""

from apps.dx.dx_layer3.dashboard.services import (
    load_timeseries_rules,
    load_crossfield_rules,
    load_category_rules,
)


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

    ts_rules = load_timeseries_rules()
    sidebar['time_series'] = []
    seen_ts = set()
    for r in ts_rules:
        name = r['detail_name']
        if name not in seen_ts:
            seen_ts.add(name)
            sidebar['time_series'].append({'name': name, 'detail_code': r['detail_code']})

    sidebar['cross_field'] = list(dict.fromkeys(
        r['section_name'] for r in load_crossfield_rules() if r.get('section_name')
    ))

    sidebar['category_spec'] = list(dict.fromkeys(
        r['section_name'] for r in load_category_rules() if r.get('section_name')
    ))

    sidebar['field_missing'] = ['TV']

    return sidebar


def _build_sidebar_groups(section):
    sidebar = _get_sidebar_items()
    return [
        {'key': 'time_series', 'icon': '📈', 'label': '시계열 이상치',
         'expanded': section == 'time_series', 'active': section == 'time_series',
         'items': [{'name': n['name'], 'detail_code': n['detail_code'], 'active': False} for n in sidebar['time_series']]},
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


def build_context(section, request):
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
