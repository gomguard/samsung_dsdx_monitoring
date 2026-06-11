"""
DX 대시보드 비즈니스 로직
"""

def get_dashboard_context():
    """
    대시보드 페이지 렌더링에 필요한 컨텍스트 데이터를 반환합니다.
    """
    return {
        'data_source': {
            'id': 'dx',
            'name': 'DX',
            'description': '미국 TV/HHP Retail, YouTube, Trend, LLM 분석 데이터 품질 모니터링',
            'color': '#0d9488',
        },
        'layers': [
            {
                'number': 1,
                'name': '기본 통계 검수',
                'name_en': 'Foundational Integrity Check',
                'description': '수집 건수 및 테이블별 데이터 현황 검증',
                'icon': 'server',
                'color': '#1a365d',
                'url': '/dx/layer1/',
            },
            {
                'number': 2,
                'name': '형식/NULL 검수',
                'name_en': 'Format & Null Validation',
                'description': 'NULL 검증, 형식 검증, 이상치 검증',
                'icon': 'cog',
                'color': '#0d9488',
                'url': '/dx/layer2/',
            },
            {
                'number': 3,
                'name': '이상치/특수 케이스 검수',
                'name_en': 'Outlier & Anomaly Detection',
                'description': '비즈니스 로직 위반 및 관련 없는 데이터 검증',
                'icon': 'search',
                'color': '#d97706',
                'url': '/dx/layer3/',
            },
            {
                'number': 4,
                'name': '검수 확인',
                'name_en': 'Review & Report',
                'description': '검수 로그, 정정 이력 및 보고서 관리',
                'icon': 'clipboard',
                'color': '#764ba2',
                'url': '/dx/layer4/',
            },
        ]
    }
