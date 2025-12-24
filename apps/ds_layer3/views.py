"""
DS Layer 3: 이상치/특수 케이스 검수
"""
from django.shortcuts import render

def index(request):
    context = {
        'layer': {
            'number': 3,
            'name': '이상치/특수 케이스 검수',
            'name_en': 'Outlier & Anomaly Detection',
            'description': '비즈니스 로직 위반 및 관련 없는 데이터 검증',
            'color': '#d97706',
        },
        'data_source': {'id': 'ds', 'name': 'DS Retail', 'color': '#1a365d'}
    }
    return render(request, 'ds_layer3/index.html', context)
