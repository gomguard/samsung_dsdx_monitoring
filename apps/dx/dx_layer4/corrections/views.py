"""
Layer 4 검수기록 페이지 뷰
"""

from django.shortcuts import render
from apps.dx.dx_layer4.common.context import build_context


def corrections(request):
    """검수기록"""
    return render(request, 'layer4/corrections.html', build_context('corrections', request))
