"""
Layer 4 공통 컨텍스트 빌더 — 사이드바, 레이아웃 등
"""

LAYER_CONTEXT = {
    'number': 4,
    'name': '검수 확인',
    'name_en': 'Review & Report',
    'color': '#764ba2',
}

SECTION_TITLES = {
    'dashboard': '대시보드',
    'check_log': '마감기록',
    'corrections': '검수기록',
    'report': '보고서',
}


def _build_sidebar_groups(section, focus=''):
    return [
        {
            'key': 'check_log',
            'icon': '✅',
            'label': '마감기록',
            'expanded': section == 'check_log',
            'active': section == 'check_log',
            'items': [
                {'name': '전체 현황', 'active': section == 'check_log'},
            ],
        },
        {
            'key': 'corrections',
            'icon': '📝',
            'label': '검수기록',
            'expanded': section == 'corrections',
            'active': section == 'corrections',
            'items': [
                {'name': 'NULL 검수', 'active': section == 'corrections' and focus == 'NULL 검수'},
                {'name': '형식 검수', 'active': section == 'corrections' and focus == '형식 검수'},
                {'name': '중복 검수', 'active': section == 'corrections' and focus == '중복 검수'},
                {'name': '크로스필드 검수', 'active': section == 'corrections' and focus == '크로스필드 검수'},
                {'name': '누락필드 검수', 'active': section == 'corrections' and focus == '누락필드 검수'},
            ],
        },
        {
            'key': 'report',
            'icon': '📋',
            'label': '보고서',
            'expanded': section == 'report',
            'active': section == 'report',
            'items': [
                {'name': '일일 보고서', 'active': section == 'report'},
            ],
        },
    ]


def build_context(section, request):
    focus = request.GET.get('focus', '')
    return {
        'layer': LAYER_CONTEXT,
        'section': section,
        'section_title': SECTION_TITLES.get(section, ''),
        'target_date': request.GET.get('date', ''),
        'focus': focus,
        'sidebar_title': 'Layer 4 검수',
        'sidebar_base_url': '/dx/layer4/',
        'sidebar_groups': _build_sidebar_groups(section, focus),
    }
