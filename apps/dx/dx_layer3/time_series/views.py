"""
Layer 3 시계열 이상치 페이지 뷰
"""

from django.shortcuts import render
from apps.dx.dx_layer3.common.context import build_context


def time_series(request):
    """시계열 이상치"""
    return render(request, 'layer3_time_series.html', build_context('time_series', request))
