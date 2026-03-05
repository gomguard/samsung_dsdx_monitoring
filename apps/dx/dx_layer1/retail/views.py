from django.shortcuts import render
from apps.dx.dx_layer1.common.context import build_context


def retail(request):
    """Retail 검증"""
    return render(request, 'dx_layer1_retail.html', build_context('retail', request))
