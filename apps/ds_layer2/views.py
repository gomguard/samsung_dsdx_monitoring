"""
DS Layer 2: 형식/NULL 검수
"""
from django.shortcuts import render

def index(request):
    context = {
        'layer': {
            'number': 2,
            'name': '형식/NULL 검수',
            'name_en': 'Format & Null Validation',
            'description': 'NULL 검증, 형식 검증, 수집률 검증',
            'color': '#0d9488',
        },
        'data_source': {'id': 'ds', 'name': 'DS Retail', 'color': '#1a365d'}
    }
    return render(request, 'ds_layer2/index.html', context)
