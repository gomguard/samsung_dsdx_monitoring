from django.shortcuts import render
from apps.dx.dx_layer1.common.context import build_context


def market_trend(request):
    """Market Trend 검증"""
    return render(request, 'dx_layer1_market_trend.html', build_context('market_trend', request))
