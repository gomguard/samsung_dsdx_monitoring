from django.shortcuts import render
from apps.dx.dx_layer1.common.context import build_context


def youtube(request):
    """YouTube 검증"""
    return render(request, 'dx_layer1_youtube.html', build_context('youtube', request))
