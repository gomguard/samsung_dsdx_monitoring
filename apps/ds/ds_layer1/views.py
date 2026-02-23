"""
DS Layer 1: 기본 통계 검수
인스턴스별/지역별 수집 현황 검증
"""

from django.shortcuts import render

LAYER_CONTEXT = {
    'layer': {
        'number': 1,
        'name': '기본 통계 검수',
        'name_en': 'Foundational Integrity Check',
        'description': '인스턴스별/지역별 수집 건수 및 완료율 검증',
        'color': '#1a365d',
    },
    'data_source': {
        'id': 'ds',
        'name': 'DS Retail',
        'name_en': 'Global Price Tracking',
        'color': '#1a365d',
    }
}


def index(request):
    """DS Layer 1 메인 페이지 - 인스턴스별 수집 현황"""
    return render(request, 'ds_layer1/index.html', LAYER_CONTEXT)


def fileserver(request):
    """파일서버 탐색 페이지"""
    return render(request, 'ds_layer1/fileserver.html', LAYER_CONTEXT)
