from django.shortcuts import render
from apps.dx.dx_layer2.common.context import build_context


def null_validation(request):
    """NULL 검증"""
    return render(request, 'layer2_null_validation.html', build_context('null_validation', request))
