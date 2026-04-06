"""
Layer 1 Dashboard API: HTTP 요청/응답 처리
"""

from django.http import JsonResponse
from apps.common.params import parse_date
from .services import get_dashboard_stats


def layer_stats(request):
    """Layer 1 통계 API"""
    target_date = parse_date(request.GET.get('date'))
    check_type_filter = request.GET.get('check_type')
    results = get_dashboard_stats(target_date, check_type_filter)
    return JsonResponse(results)
