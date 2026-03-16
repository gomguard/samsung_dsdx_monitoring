"""
DS Layer 2 API: 데이터 품질 검수 HTTP 요청/응답 처리
"""

from datetime import datetime, timedelta
from django.http import JsonResponse
from apps.common.response import safe_error

from apps.ds.ds_layer2.stats.services import get_layer_stats, get_table_null_detail
from apps.ds.ds_layer4.report.services import get_report_status


def layer_stats(request):
    """DS Layer 2 전체 데이터 품질 통계 API"""
    date_str = request.GET.get('date')
    batch_view = request.GET.get('batch_view', 'final')

    if date_str:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    else:
        target_date = (datetime.now() - timedelta(days=1)).date()

    data = get_layer_stats(target_date, batch_view)
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

    if date_str:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    else:
        target_date = (datetime.now() - timedelta(days=1)).date()

    result = get_table_null_detail(target_date, table_name, error_type, page, page_size, start_time, end_time, sort_by, sort_order)
    status = result.pop('status', 200) if 'status' in result else 200
    return JsonResponse(result, status=status)


def report_status(request):
    """날짜별 저장/마감 현황 조회 API"""
    date_str = request.GET.get('date')
    if not date_str:
        date_str = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')

    try:
        result = get_report_status(date_str)
        return JsonResponse(result)
    except Exception as e:
        return safe_error(e, success=False)
