"""
DS Layer 3: SKU 이상치 반복 패턴 분석
"""
from django.shortcuts import render

def index(request):
    context = {
        'layer': {
            'number': 3,
            'name': 'SKU 이상치 추적',
            'name_en': 'SKU Anomaly Pattern Analysis',
            'description': 'SKU별 이상치 반복 패턴 분석 (마감 데이터 + 실시간)',
            'color': '#d97706',
        },
        'data_source': {'id': 'ds', 'name': 'DS Retail', 'color': '#1a365d'}
    }
    return render(request, 'ds_layer3/index.html', context)
