"""
DS Layer 5: 전문가 전수 검수
"""
from django.shortcuts import render

def index(request):
    context = {
        'layer': {
            'number': 5,
            'name': '전문가 전수 검수',
            'name_en': 'The Human Firewall',
            'description': '검토 필요 태그 기반 전문가 최종 승인',
            'color': '#475569',
        },
        'data_source': {'id': 'ds', 'name': 'DS Retail', 'color': '#1a365d'}
    }
    return render(request, 'ds_layer5/index.html', context)
