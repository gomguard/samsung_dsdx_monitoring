from django.shortcuts import render
from apps.dx.dx_layer1.common.context import build_context

def dashboard(request):
    """Layer 1 대시보드"""
    return render(request, 'dx_layer1_dashboard.html', build_context('dashboard', request))
