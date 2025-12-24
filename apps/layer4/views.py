"""
Layer 4: 문맥/의미 기반 검증 (Context & Meaning Verification)
- 데이터 내 문맥 불일치 및 의미적 모순 검증
- LLM을 이용한 심층 의미 분석
"""

from django.shortcuts import render


def index(request):
    """Layer 4 대시보드"""
    context = {
        'layer': {
            'number': 4,
            'name': '문맥/의미 검증',
            'name_en': 'Context & Meaning Verification',
            'color': '#7c3aed',
        }
    }
    return render(request, 'layer4/index.html', context)
