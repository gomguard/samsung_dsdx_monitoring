"""
Macro Layer1 API: 원본 데이터 조회
"""

from datetime import datetime, timedelta
from django.http import JsonResponse
from apps.common.response import log_error
from .macro_services import get_macro_raw_data, _TABLE_MAP


def macro_raw_data(request):
    """Macro 원본 데이터 조회 API"""
    check_type = request.GET.get('check_type', '')
    date_str = request.GET.get('date')

    if check_type not in _TABLE_MAP:
        return JsonResponse({'error': '잘못된 check_type입니다.'}, status=400)

    if not date_str:
        target_date = (datetime.now() - timedelta(days=1)).date()
    else:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()

    try:
        result = get_macro_raw_data(check_type, target_date)
        return JsonResponse(result)
    except Exception as e:
        return JsonResponse({'error': log_error(e)})
