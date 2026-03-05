"""
Layer 4: 검수 확인 / 보고서 (Review & Report)
- 마감기록: Layer 1 수집 마감 확인 이력
- 검수기록: Layer 2/3에서 수행한 검수(수정/정상처리) 이력 확인
- 보고서: 일일 보고서 자동 생성
"""

from django.shortcuts import render


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
                {'name': '일일 보고서', 'active': section == 'report' and focus == '일일 보고서'},
                {'name': '원인별 현황', 'active': section == 'report' and focus == '원인별 현황'},
            ],
        },
    ]


def _build_context(section, request):
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


def dashboard(request):
    """Layer 4 대시보드"""
    return render(request, 'layer4/dashboard.html', _build_context('dashboard', request))


def check_log(request):
    """마감기록"""
    return render(request, 'layer4/check_log.html', _build_context('check_log', request))


def check_log_detail(request):
    """마감기록 상세"""
    return render(request, 'layer4/check_log_detail.html', _build_context('check_log', request))


def corrections(request):
    """검수기록"""
    return render(request, 'layer4/corrections.html', _build_context('corrections', request))


def report(request):
    """보고서"""
    return render(request, 'layer4/report.html', _build_context('report', request))
