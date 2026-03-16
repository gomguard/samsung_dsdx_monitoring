"""
DS Layer 4: 보고서 관리
"""
from django.shortcuts import render


def index(request):
    context = {
        'layer': {
            'number': 4,
            'name': '보고서 관리',
            'name_en': 'Report Management',
            'description': '저장된 이상치 보고서 관리 및 마감',
            'color': '#7e6b9b',
        },
        'data_source': {'id': 'ds', 'name': 'DS Retail', 'color': '#1a365d'}
    }
    return render(request, 'ds_layer4/index.html', context)
