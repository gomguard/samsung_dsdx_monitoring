"""
DS Layer 4: 문맥/의미 검증
"""
from django.shortcuts import render

def index(request):
    context = {
        'layer': {
            'number': 4,
            'name': '문맥/의미 검증',
            'name_en': 'Context & Meaning Verification',
            'description': '데이터 내 문맥 불일치 및 의미적 모순 검증',
            'color': '#7c3aed',
        },
        'data_source': {'id': 'ds', 'name': 'DS Retail', 'color': '#1a365d'}
    }
    return render(request, 'ds_layer4/index.html', context)
