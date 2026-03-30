"""
DS Layer 2 Stats API: 데이터 품질 검수 통계 HTTP 요청/응답 처리
"""
from datetime import datetime, timedelta
from django.http import JsonResponse
from . import stats_services

def layer_stats(request):
    """DS Layer 2 전체 데이터 품질 통계 API"""
    date_str = request.GET.get('date')
    batch_view = request.GET.get('batch_view', 'final')
    target_date = datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else (datetime.now() - timedelta(days=1)).date()
    data = stats_services.get_layer_stats(target_date, batch_view)
    return JsonResponse(data)

def table_null_detail(request):
    """특정 테이블의 비정상 데이터 상세 조회 API"""
    date_str = request.GET.get('date')
    table_name = request.GET.get('table')
    error_type = request.GET.get('error_type', 'title_null')
    try:
        page = max(1, int(request.GET.get('page', 1)))
        page_size = min(int(request.GET.get('page_size', 50)), 200)
    except (ValueError, TypeError):
        return JsonResponse({'error': '잘못된 페이지 파라미터'}, status=400)

    start_time = request.GET.get('start_time')
    end_time = request.GET.get('end_time')
    sort_by = request.GET.get('sort_by', 'crawl_strdatetime')
    sort_order = request.GET.get('sort_order', 'asc')

    target_date = datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else (datetime.now() - timedelta(days=1)).date()
    result = stats_services.get_table_null_detail(target_date, table_name, error_type, page, page_size, start_time, end_time, sort_by, sort_order)
    status = result.pop('status', 200) if result and 'status' in result else 200
    if not result:
        return JsonResponse({'error': 'Data missing'}, status=500)
    return JsonResponse(result, status=status)
