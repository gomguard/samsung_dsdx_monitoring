from django.shortcuts import render
from apps.dx.dx_layer1.common.context import build_context


def market_demand(request):
    """Market Demand 검증"""
    return render(request, 'dx_layer1_market_demand.html', build_context('market_demand', request))
