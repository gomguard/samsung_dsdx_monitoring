"""
Layer 4 마감기록 페이지 뷰
"""

from django.shortcuts import render
from apps.dx.dx_layer4.common.context import build_context


def check_log(request):
    """마감기록"""
    return render(request, 'layer4/check_log.html', build_context('check_log', request))


def check_log_detail(request):
    """마감기록 상세"""
    return render(request, 'layer4/check_log_detail.html', build_context('check_log', request))
