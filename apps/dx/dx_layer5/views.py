"""
Layer 5: 전문가 전수 검수 (The Human Firewall)
- '검토 필요' 태그 기반 전문가의 최종 승인
- 데이터의 최종 품질은 기계가 아닌 전문가가 보증
"""

from django.shortcuts import render


def index(request):
    """Layer 5 대시보드"""
    context = {
        'layer': {
            'number': 5,
            'name': '전문가 전수 검수',
            'name_en': 'The Human Firewall',
            'color': '#475569',
        }
    }
    return render(request, 'layer5/index.html', context)
