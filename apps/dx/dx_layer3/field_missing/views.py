"""
Layer 3 필드 누락 페이지 뷰
"""

from django.shortcuts import render
from apps.dx.dx_layer3.common.context import build_context


def field_missing(request):
    """필드 누락"""
    return render(request, 'layer3_field_missing.html', build_context('field_missing', request))
