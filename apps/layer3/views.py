"""
Layer 3: 이상치/특수 케이스 검수 (Outlier & Anomaly Detection)
- 비즈니스 로직 위반 및 관련 없는 데이터 검증
- LLM을 이용한 값 검증, '검토 필요' 태그 부착
"""

from django.shortcuts import render


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


def _build_context(section, request):
    return {
        'layer': LAYER_CONTEXT,
        'section': section,
        'section_title': SECTION_TITLES.get(section, ''),
        'target_date': request.GET.get('date', ''),
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
