"""
DS Layer 2 API: 데이터 품질 검수 + 리테일러 마감 HTTP 요청/응답 처리
"""

import json
from datetime import datetime, timedelta
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from apps.common.response import safe_error

from apps.ds.ds_layer2.stats.services import get_layer_stats, get_table_null_detail
from apps.ds.ds_layer2.report.services import (
    get_retailer_save_status, save_retailer, delete_retailer
)
from apps.ds.ds_layer4.report.services import is_report_closed


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
    """리테일러 저장 현황 + 보고서 마감 여부 조회 API"""
    date_str = request.GET.get('date')
    if not date_str:
        date_str = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')

    try:
        save_result = get_retailer_save_status(date_str)
        close_result = is_report_closed(date_str)
        return JsonResponse({
            'success': True,
            'date': date_str,
            'is_closed': close_result.get('is_closed', False),
            'saved_retailers': save_result.get('saved_retailers', {})
        })
    except Exception as e:
        return safe_error(e, success=False)


@require_http_methods(["POST"])
def report_save(request):
    """리테일러 마감 저장 API"""
    try:
        body = json.loads(request.body)
        result = save_retailer(
            crawl_date=body.get('crawl_date'),
            retailer=body.get('retailer'),
            anomalies=body.get('anomalies', []),
            memo=body.get('memo', ''),
            user_id=body.get('user_id', 'system')
        )
        return JsonResponse(result)
    except Exception as e:
        return safe_error(e, success=False)


@require_http_methods(["POST"])
def report_delete(request):
    """리테일러 마감 삭제 API"""
    try:
        body = json.loads(request.body)
        result = delete_retailer(
            crawl_date=body.get('crawl_date'),
            retailer=body.get('retailer'),
            user_id=body.get('user_id', 'system')
        )
        return JsonResponse(result)
    except Exception as e:
        return safe_error(e, success=False)
