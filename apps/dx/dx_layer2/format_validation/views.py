from django.shortcuts import render
from apps.dx.dx_layer2.common.context import build_context


def format_validation(request):
    """형식 검증"""
    return render(request, 'layer2/format_validation.html', build_context('format_validation', request))
