"""
Layer 1 공통 context — 상수 및 사이드바 헬퍼
"""

LAYER_CONTEXT = {
    'number': 1,
    'name': '기본 통계 검수',
    'name_en': 'Foundational Integrity Check',
    'color': '#1a365d',
}

SECTION_TITLES = {
    'dashboard': '대시보드',
    'retail': 'Retail',
    'sentiment': 'Retail 감성분석',
    'youtube': 'YouTube',
    'market_trend': 'Market Trend',
    'market_demand': 'Market 수요증감율',
    'market_competitor': 'Market Competitor',
    'market_competitor_event': 'Market Competitor Event',
    'market_promotion': 'Market Promotion',
}

SIDEBAR_GROUPS_DEF = [
    {
        'key': 'daily',
        'icon': '📦',
        'label': '데일리 검증',
        'sections': ['retail', 'sentiment', 'youtube', 'market_trend', 'market_demand'],
    },
    {
        'key': 'period',
        'icon': '📅',
        'label': '분석대상일별 검증',
        'sections': ['market_competitor', 'market_competitor_event', 'market_promotion'],
    },
]


def _build_sidebar_groups(section):
    groups = []
    for g in SIDEBAR_GROUPS_DEF:
        groups.append({
            'key': g['key'],
            'icon': g['icon'],
            'label': g['label'],
            'expanded': section in g['sections'],
            'active': section in g['sections'],
            'items': [
                {'name': SECTION_TITLES[s], 'active': section == s}
                for s in g['sections']
            ],
        })
    return groups


def build_context(section, request):
    return {
        'layer': LAYER_CONTEXT,
        'section': section,
        'section_title': SECTION_TITLES.get(section, ''),
        'section_titles': SECTION_TITLES,
        'target_date': request.GET.get('date', ''),
        'sidebar_title': 'Layer 1 검증',
        'sidebar_base_url': '/dx/layer1/',
        'sidebar_groups': _build_sidebar_groups(section),
    }
