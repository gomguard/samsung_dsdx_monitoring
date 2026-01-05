"""
DX Report API: DX 모니터링 보고서 데이터 API
"""

from django.http import JsonResponse
from datetime import datetime, timedelta


def report_stats(request):
    """DX 모니터링 보고서 통계 API (현재는 정적 데이터)"""
    data = {
        'timestamp': datetime.now().isoformat(),
        'data_source': 'dx',
        'summary': {
            'layer1_items': 6,
            'layer2_items': 15,
            'layer3_items': 12,
            'total_items': 33
        }
    }
    return JsonResponse(data)
