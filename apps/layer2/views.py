"""
Layer 2: 형식/NULL 검수 (Formatting & Null Validation)
- NULL 검증: 필수 필드의 NULL 또는 빈값 검증
- 형식 검증: 데이터 형식 및 패턴 검증
- 이상치 검증: 논리적 오류 및 이상값 탐지
"""

from django.shortcuts import render


def index(request):
    """Layer 2 대시보드"""
    context = {
        'layer': {
            'number': 2,
            'name': '형식/NULL 검수',
            'name_en': 'Formatting & Null Validation',
            'color': '#0d9488',
        }
    }
    return render(request, 'layer2/index.html', context)
