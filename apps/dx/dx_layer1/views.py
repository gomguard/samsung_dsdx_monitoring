"""
Layer 1: 기본 통계 검수 (Foundational Integrity Check)
- 인프라 오류 및 기본 데이터 누락 검증
- SQL 및 Python을 이용한 기본 통계 검증
"""

from django.shortcuts import render


def index(request):
    """Layer 1 대시보드"""
    context = {
        'layer': {
            'number': 1,
            'name': '기본 통계 검수',
            'name_en': 'Foundational Integrity Check',
            'color': '#1a365d',
        },
        'checks': [
            {
                'name': '수집 행 개수 검증',
                'description': '수집 직후 행의 개수가 예상 범위 내에 있는지 확인',
            },
            {
                'name': '필수 컬럼 존재 확인',
                'description': '필수 컬럼이 모두 존재하는지 확인',
            },
            {
                'name': '인프라 오류 검증',
                'description': 'AWS EC2 작동 오류, 메모리 이슈, 네트워크 문제 등 확인',
            },
        ]
    }
    return render(request, 'layer1/index.html', context)
