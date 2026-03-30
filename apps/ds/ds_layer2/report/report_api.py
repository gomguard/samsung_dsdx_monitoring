"""
DS Layer 2 Report API: 데이터 오류 검수 리테일러 마감 HTTP 파이프라인
"""
import json
from datetime import datetime, timedelta
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from apps.common.response import safe_error
from apps.ds.ds_layer4.report.services import is_report_closed
from . import report_services

def report_status(request):
    """리테일러 저장 현황 + 보고서 마감 여부 조회 API"""
    date_str = request.GET.get('date')
    if not date_str: date_str = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    try:
        save_result = report_services.get_retailer_save_status(date_str)
        close_result = is_report_closed(date_str)
        return JsonResponse({'success': True, 'date': date_str, 'is_closed': close_result.get('is_closed', False), 'saved_retailers': save_result.get('saved_retailers', {})})
    except Exception as e:
        return safe_error(e, success=False)

@require_http_methods(["POST"])
def report_save(request):
    """리테일러 마감 저장 API"""
    try:
        body = json.loads(request.body)
        result = report_services.save_retailer(body.get('crawl_date'), body.get('retailer'), body.get('anomalies', []), body.get('memo', ''), body.get('user_id', 'system'))
        return JsonResponse(result)
    except Exception as e:
        return safe_error(e, success=False)

@require_http_methods(["POST"])
def report_delete(request):
    """리테일러 마감 삭제 API"""
    try:
        body = json.loads(request.body)
        result = report_services.delete_retailer(body.get('crawl_date'), body.get('retailer'), body.get('user_id', 'system'))
        return JsonResponse(result)
    except Exception as e:
        return safe_error(e, success=False)
