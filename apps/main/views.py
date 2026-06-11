"""
메인 대시보드 뷰
5단계 방어 체계 모니터링 시스템의 메인 페이지
"""

from django.shortcuts import render


def index(request):
    """메인 페이지 - DS/DX 선택 화면"""
    context = {
        'data_sources': [
            {
                'id': 'dx',
                'name': 'DX_SEA',
                'name_en': 'SEA Retail Monitoring',
                'description': 'SEA TV/HHP/REF/LDY 리테일 데이터 모니터링',
                'sub_description': 'Amazon, Bestbuy, Walmart, Lowe’s 리테일 데이터',
                'icon': 'tv',
                'color': '#0d9488',
                'url': '/dx/',
                'tables': ['TV Retail', 'REF Retail', 'LDY Retail', 'YouTube', 'Sentiment', 'Market Share'],
            },
            {
                'id': 'ds',
                'name': 'DS Retail',
                'name_en': 'Global Price Tracking',
                'description': '글로벌 가격 추적 데이터 모니터링',
                'sub_description': '17개국 리테일러 가격 추적 데이터',
                'icon': 'globe',
                'color': '#1a365d',
                'url': '/ds/',
                'tables': ['Amazon', 'Bestbuy', 'Danawa', 'Currys', 'MediaMarkt', 'Fnac', '...'],
            },
        ]
    }
    return render(request, 'main/index.html', context)


def ds_dashboard(request):
    """DS 대시보드 페이지"""
    context = {
        'data_source': {
            'id': 'ds',
            'name': 'DS Retail',
            'name_en': 'Global Price Tracking',
            'color': '#1a365d',
        },
        'layers': [
            {
                'number': 1,
                'name': '기본 통계 검수',
                'name_en': 'Foundational Integrity Check',
                'description': '수집 건수 및 테이블별 데이터 현황 검증',
                'icon': 'server',
                'color': '#1a365d',
                'url': '/ds/layer1/',
            },
            {
                'number': 2,
                'name': '데이터 오류 검수',
                'name_en': 'Data Error Detection',
                'description': 'NULL 검증, 형식 검증, 데이터 오류 탐지',
                'icon': 'cog',
                'color': '#0d9488',
                'url': '/ds/layer2/',
            },
            {
                'number': 3,
                'name': '연속 오류 추적',
                'name_en': 'Recurring Error Tracking',
                'description': '신규 에러 및 반복 에러 추적',
                'icon': 'search',
                'color': '#d97706',
                'url': '/ds/layer3/',
            },
        ],
        'extra_layers': [
            {
                'number': 4,
                'name': '보고서 관리',
                'name_en': 'Report Management',
                'description': '저장된 이상치 보고서 관리 및 마감',
                'icon': 'clipboard',
                'color': '#7e6b9b',
                'url': '/ds/layer4/',
            },
        ]
    }
    return render(request, 'main/ds_dashboard.html', context)
