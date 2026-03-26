"""
Layer 2 Dashboard: 대시보드 페이지 렌더링
"""

from django.shortcuts import render
from apps.dx.dx_layer2.common.context import build_context


def dashboard(request):
    """Layer 2 대시보드"""
    return render(request, 'dashboard.html', build_context('dashboard', request))
