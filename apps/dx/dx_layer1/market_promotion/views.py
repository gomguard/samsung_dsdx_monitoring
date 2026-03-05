from django.shortcuts import render
from apps.dx.dx_layer1.common.context import build_context


def market_promotion(request):
    """Market Promotion 검증"""
    return render(request, 'dx_layer1_market_promotion.html', build_context('market_promotion', request))
