"""
Layer 4 보고서 페이지 뷰
"""

from django.shortcuts import render
from apps.dx.dx_layer4.common.context import build_context


def report(request):
    """보고서"""
    return render(request, 'layer4/report.html', build_context('report', request))
