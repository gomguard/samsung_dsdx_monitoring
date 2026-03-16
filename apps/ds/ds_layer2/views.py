"""
DS Layer 2: 데이터 오류 검수
"""
from django.shortcuts import render

def index(request):
    context = {
        'layer': {
            'number': 2,
            'name': '데이터 오류 검수',
            'name_en': 'Data Error Detection',
            'description': 'NULL 검증, 형식 검증, 데이터 오류 탐지',
            'color': '#0d9488',
        },
        'data_source': {'id': 'ds', 'name': 'DS Retail', 'color': '#1a365d'}
    }
    return render(request, 'ds_layer2/index.html', context)
