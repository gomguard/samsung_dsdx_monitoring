from django.shortcuts import render
from apps.dx.dx_layer4.common.context import build_context


def tools(request):
    """도구 모음"""
    return render(request, 'layer4/tools.html', build_context('tools', request))
