from django.shortcuts import render
from apps.dx.dx_layer1.common.context import build_context

def market_competitor(request):
    """Market Competitor 검증"""
    return render(request, 'dx_layer1_market_competitor.html', build_context('market_competitor', request))

def market_competitor_event(request):
    """Market Competitor Event 검증"""
    return render(request, 'dx_layer1_market_competitor_event.html', build_context('market_competitor_event', request))

def market_demand(request):
    """Market Demand 검증"""
    return render(request, 'dx_layer1_market_demand.html', build_context('market_demand', request))

def market_promotion(request):
    """Market Promotion 검증"""
    return render(request, 'dx_layer1_market_promotion.html', build_context('market_promotion', request))

def market_trend(request):
    """Market Trend 검증"""
    return render(request, 'dx_layer1_market_trend.html', build_context('market_trend', request))

def retail(request):
    """Retail 검증"""
    return render(request, 'dx_layer1_retail.html', build_context('retail', request))

def sentiment(request):
    """Sentiment 검증"""
    return render(request, 'dx_layer1_sentiment.html', build_context('sentiment', request))

def youtube(request):
    """YouTube 검증"""
    return render(request, 'dx_layer1_youtube.html', build_context('youtube', request))

def macro(request):
    """Macro 검증"""
    check_type = request.GET.get('check_type', '')
    return render(request, 'dx_layer1_macro.html', build_context(check_type or 'macro', request))


def dashboard(request):
    """Layer 1 대시보드"""
    return render(request, 'dx_layer1_dashboard.html', build_context('dashboard', request))
