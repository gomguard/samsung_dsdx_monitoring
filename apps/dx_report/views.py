"""
DX 모니터링 보고 페이지
"""

from django.shortcuts import render


def index(request):
    """DX 모니터링 보고 페이지"""
    return render(request, 'dx_report/index.html')
