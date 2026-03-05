from django.shortcuts import render
from apps.dx.dx_layer1.common.context import build_context


def market_competitor_event(request):
    """Market Competitor Event 검증"""
    return render(request, 'dx_layer1_market_competitor_event.html', build_context('market_competitor_event', request))
