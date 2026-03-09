"""
Layer 3 크로스 필드 검증 페이지 뷰
"""

from django.shortcuts import render
from apps.dx.dx_layer3.common.context import build_context


def cross_field(request):
    """크로스 필드 검증"""
    return render(request, 'layer3/cross_field.html', build_context('cross_field', request))
