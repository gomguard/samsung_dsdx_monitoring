from django.http import JsonResponse
from datetime import datetime, timedelta
from apps.common.db import get_dx_connection
from apps.common.response import log_error
from . import services


def youtube_raw_data(request):
    """
    YouTube 원본 데이터 조회 API
    - category: TV 또는 HHP
    - date: 조회 날짜 (YYYY-MM-DD)
    - data_type: logs, videos, comments (기본: logs)
    """
    category = request.GET.get('category', 'TV')
    date_str = request.GET.get('date')
    data_type = request.GET.get('data_type', 'logs')

    if not date_str:
        target_date = (datetime.now() - timedelta(days=1)).date()
    else:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()

    try:
        conn = get_dx_connection()
        cursor = conn.cursor()
        result = services.get_youtube_raw_data(cursor, category, data_type, target_date)
        cursor.close()
        conn.close()
        return JsonResponse(result)
    except Exception as e:
        return JsonResponse({'error': log_error(e)})
