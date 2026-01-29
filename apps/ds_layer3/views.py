"""
DS Layer 3: 연속 오류 추적
"""
from django.shortcuts import render

def index(request):
    context = {
        'layer': {
            'number': 3,
            'name': '연속 오류 추적',
            'name_en': 'Recurring Error Tracking',
            'description': '신규 에러 및 반복 에러 추적',
            'color': '#d97706',
        },
        'data_source': {'id': 'ds', 'name': 'DS Retail', 'color': '#1a365d'}
    }
    return render(request, 'ds_layer3/index.html', context)
