"""
Layer 4 대시보드 페이지 뷰
"""

from django.shortcuts import render
from apps.dx.dx_layer4.common.context import build_context


def dashboard(request):
    """Layer 4 대시보드"""
    return render(request, 'layer4/dashboard.html', build_context('dashboard', request))
