"""
Layer 3 카테고리별 특성 페이지 뷰
"""

from django.shortcuts import render
from apps.dx.dx_layer3.common.context import build_context


def category_spec(request):
    """카테고리별 특성"""
    return render(request, 'layer3/category_spec.html', build_context('category_spec', request))
