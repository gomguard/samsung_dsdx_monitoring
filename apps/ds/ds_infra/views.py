"""
인프라 모니터링: EC2 인스턴스 상태 확인 및 시작/종료
"""

from django.shortcuts import render


def index(request):
    """인프라 모니터링 대시보드"""
    context = {
        'page_title': 'EC2 인스턴스 현황',
    }
    return render(request, 'ds_infra/index.html', context)
