"""
Layer 4 보고서 API — 보고서 데이터 조회
"""

from django.http import JsonResponse
from apps.common.response import safe_error
from apps.common.params import parse_date
from .services import get_report_data


def report_data(request):
    """보고서 데이터 조회 (GET)"""
    target_date = parse_date(request.GET.get('date'))
    if target_date is None:
        return JsonResponse({'error': '날짜 형식이 올바르지 않습니다.'}, status=400)

    try:
        return JsonResponse(get_report_data(target_date))
    except Exception as e:
        return safe_error(e)
