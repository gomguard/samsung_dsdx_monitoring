"""
DX 대시보드 — 페이지 뷰
"""

from django.shortcuts import render
from .dashboard.dashboard_services import get_dashboard_context

def dashboard(request):
    """DX 대시보드 페이지"""
    context = get_dashboard_context()
    return render(request, 'dx_dashboard.html', context)
