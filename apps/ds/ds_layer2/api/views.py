"""
DS Layer 2 API: HTTP 요청/응답 처리
"""

import json
from datetime import datetime, timedelta, date
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from apps.common.response import safe_error

from apps.ds.ds_layer2.stats.services import get_layer_stats, get_table_null_detail
from apps.ds.ds_layer2.report.services import (
    save_report, delete_report, update_report, update_daily_memo,
    save_all_reports, save_file_info, close_report, cancel_close_report,
    get_report_status, get_report_list, get_file_size_history
)
from apps.ds.ds_layer2.screenshot.services import (
    get_screenshot_url as _get_screenshot_url,
    trigger_screenshot_capture, get_screenshot_status,
    delete_screenshots, upload_screenshot
)


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


@require_http_methods(["POST"])
def report_save(request):
    """리테일러별 이상치 데이터 저장 API"""
    try:
        body = json.loads(request.body)
        result = save_report(
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
    """리테일러별 저장된 데이터 삭제 API"""
    try:
        body = json.loads(request.body)
        result = delete_report(
            crawl_date=body.get('crawl_date'),
            retailer=body.get('retailer'),
            user_id=body.get('user_id', 'system')
        )
        return JsonResponse(result)
    except Exception as e:
        return safe_error(e, success=False)


@require_http_methods(["POST"])
def report_update(request):
    """이상치 데이터 수정 API"""
    try:
        body = json.loads(request.body)
        result = update_report(body)
        return JsonResponse(result)
    except Exception as e:
        return safe_error(e, success=False)


@require_http_methods(["POST"])
def report_daily_update(request):
    """일별 보고서 메모 수정 API"""
    try:
        body = json.loads(request.body)
        result = update_daily_memo(body)
        return JsonResponse(result)
    except Exception as e:
        return safe_error(e, success=False)


@require_http_methods(["POST"])
def report_save_all(request):
    """미저장 리테일러 일괄 현황 저장 API"""
    try:
        body = json.loads(request.body)
        result = save_all_reports(
            crawl_date=body.get('crawl_date'),
            user_id=body.get('user_id', 'system')
        )
        return JsonResponse(result)
    except Exception as e:
        return safe_error(e, success=False)


@require_http_methods(["POST"])
def report_save_file_info(request):
    """파일서버 파일 정보 전체 업데이트 API"""
    try:
        body = json.loads(request.body)
        result = save_file_info(
            crawl_date=body.get('crawl_date'),
            user_id=body.get('user_id', 'system')
        )
        return JsonResponse(result)
    except Exception as e:
        return safe_error(e, success=False)


@require_http_methods(["POST"])
def report_close(request):
    """일별 최종 마감 API"""
    try:
        body = json.loads(request.body)
        result = close_report(
            crawl_date=body.get('crawl_date'),
            user_id=body.get('user_id', 'system')
        )
        return JsonResponse(result)
    except Exception as e:
        return safe_error(e, success=False)


@require_http_methods(["POST"])
def report_cancel_close(request):
    """마감 취소 API"""
    try:
        body = json.loads(request.body)
        result = cancel_close_report(
            crawl_date=body.get('crawl_date'),
            user_id=body.get('user_id', 'system'),
            memo=body.get('memo', '')
        )
        return JsonResponse(result)
    except Exception as e:
        return safe_error(e, success=False)


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


def report_list(request):
    """저장된 이상치 목록 조회 API"""
    date_str = request.GET.get('date')
    retailer_filter = request.GET.get('retailer')
    view_mode = request.GET.get('view', 'status')

    if not date_str:
        date_str = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')

    try:
        result = get_report_list(date_str, retailer_filter, view_mode)
        return JsonResponse(result)
    except Exception as e:
        return safe_error(e, success=False)


def get_screenshot_url(request):
    """스크린샷 이미지 URL 조회 API"""
    file_id = request.GET.get('file_id')
    if not file_id:
        return JsonResponse({'success': False, 'error': 'file_id is required'})

    try:
        result = _get_screenshot_url(file_id)
        return JsonResponse(result)
    except Exception as e:
        return safe_error(e, success=False)


def screenshot_capture(request):
    """SSM을 통해 EC2 인스턴스에서 스크린샷 캡쳐 명령 실행 API"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST 요청만 허용됩니다.'}, status=405)

    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': '잘못된 요청 형식입니다.'}, status=400)

    result = trigger_screenshot_capture(
        retailer=body.get('retailer'),
        crawl_date=body.get('crawl_date'),
        username=request.user.username if request.user.is_authenticated else ''
    )
    status = result.pop('status', 200) if 'status' in result else 200
    return JsonResponse(result, status=status)


@require_http_methods(["GET"])
def report_file_size_history(request):
    """최근 N일간 리테일러별 파일 용량 조회"""
    end_date_str = request.GET.get('end_date')
    try:
        days = max(1, min(int(request.GET.get('days', 7)), 90))
    except (ValueError, TypeError):
        days = 7

    if end_date_str:
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
    else:
        end_date = date.today() - timedelta(days=1)

    try:
        result = get_file_size_history(end_date, days)
        return JsonResponse(result)
    except Exception as e:
        return safe_error(e, success=False)


@require_http_methods(["GET"])
def screenshot_status(request):
    """리테일러별 스크린샷 캡쳐 상태 조회 API"""
    retailer = request.GET.get('retailer')
    crawl_date = request.GET.get('crawl_date')

    if not retailer or not crawl_date:
        return JsonResponse({'error': '리테일러와 날짜가 필요합니다.'}, status=400)

    try:
        result = get_screenshot_status(retailer, crawl_date)
        return JsonResponse(result)
    except Exception as e:
        return safe_error(e, success=False)


def screenshot_delete(request):
    """스크린샷 삭제 API"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST 요청만 허용됩니다.'}, status=405)

    try:
        body = json.loads(request.body)
        result = delete_screenshots(body.get('anomaly_ids', []))
        return JsonResponse(result)
    except Exception as e:
        return safe_error(e, success=False)


def screenshot_upload(request):
    """스크린샷 수동 업로드 API"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST 요청만 허용됩니다.'}, status=405)

    try:
        uploaded_file = request.FILES.get('file')
        anomaly_id = request.POST.get('anomaly_id')

        if not uploaded_file or not anomaly_id:
            return JsonResponse({'success': False, 'error': '파일과 anomaly_id가 필요합니다.'})

        result = upload_screenshot(
            file_obj=uploaded_file,
            anomaly_id=int(anomaly_id),
            username=request.user.username if request.user.is_authenticated else ''
        )
        return JsonResponse(result)
    except Exception as e:
        return safe_error(e, success=False)
