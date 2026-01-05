"""
DS 모니터링 보고 페이지
"""

from django.shortcuts import render


def index(request):
    """DS 모니터링 보고 페이지"""
    return render(request, 'ds_report/index.html')
