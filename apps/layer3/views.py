"""
Layer 3: 이상치/특수 케이스 검수 (Outlier & Anomaly Detection)
- 비즈니스 로직 위반 및 관련 없는 데이터 검증
- LLM을 이용한 값 검증, '검토 필요' 태그 부착
"""

from django.shortcuts import render


def index(request):
    """Layer 3 대시보드"""
    context = {
        'layer': {
            'number': 3,
            'name': '이상치/특수 케이스 검수',
            'name_en': 'Outlier & Anomaly Detection',
            'color': '#d97706',
        }
    }
    return render(request, 'layer3/index.html', context)
