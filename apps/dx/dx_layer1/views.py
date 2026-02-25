"""
Layer 1: 기본 통계 검수 (Foundational Integrity Check)
- 인프라 오류 및 기본 데이터 누락 검증
- SQL 및 Python을 이용한 기본 통계 검증
"""

from django.shortcuts import render


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


def _build_context(section, request):
    return {
        'layer': LAYER_CONTEXT,
        'section': section,
        'section_title': SECTION_TITLES.get(section, ''),
        'section_titles': SECTION_TITLES,
        'target_date': request.GET.get('date', ''),
    }



def dashboard(request):
    """Layer 1 대시보드 (사이드바 구조)"""
    return render(request, 'layer1/dashboard.html', _build_context('dashboard', request))


def retail(request):
    """Retail 검증"""
    return render(request, 'layer1/retail.html', _build_context('retail', request))


def sentiment(request):
    """Sentiment 검증"""
    return render(request, 'layer1/sentiment.html', _build_context('sentiment', request))


def youtube(request):
    """YouTube 검증"""
    return render(request, 'layer1/youtube.html', _build_context('youtube', request))


def market_trend(request):
    """Market Trend 검증"""
    return render(request, 'layer1/market_trend.html', _build_context('market_trend', request))


def market_demand(request):
    """Market Demand 검증"""
    return render(request, 'layer1/market_demand.html', _build_context('market_demand', request))


def market_competitor(request):
    """Market Competitor 검증"""
    return render(request, 'layer1/market_competitor.html', _build_context('market_competitor', request))


def market_competitor_event(request):
    """Market Competitor Event 검증"""
    return render(request, 'layer1/market_competitor_event.html', _build_context('market_competitor_event', request))


def market_promotion(request):
    """Market Promotion 검증"""
    return render(request, 'layer1/market_promotion.html', _build_context('market_promotion', request))
