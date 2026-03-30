"""
DS Layer 4 Screenshot API: HTTP 요청/응답 처리 컨트롤러
"""
import json
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from apps.common.response import safe_error
from . import screenshot_services

def get_screenshot_url(request):
    """스크린샷 이미지 URL 조회 API"""
    file_id = request.GET.get('file_id')
    if not file_id:
        return JsonResponse({'success': False, 'error': 'file_id is required'})

    try:
        result = screenshot_services.get_screenshot_url(file_id)
        return JsonResponse(result)
    except Exception as e:
        return safe_error(e, success=False)


@require_http_methods(["POST"])
def screenshot_capture(request):
    """SSM을 통해 EC2 인스턴스에서 스크린샷 캡쳐 명령 실행 API"""
    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': '잘못된 요청 형식입니다.'}, status=400)

    result = screenshot_services.trigger_screenshot_capture(
        retailer=body.get('retailer'),
        crawl_date=body.get('crawl_date'),
        username=request.user.username if request.user.is_authenticated else ''
    )
    status = result.pop('status', 200) if 'status' in result else 200
    return JsonResponse(result, status=status)


@require_http_methods(["GET"])
def screenshot_status(request):
    """리테일러별 스크린샷 캡쳐 상태 조회 API"""
    retailer = request.GET.get('retailer')
    crawl_date = request.GET.get('crawl_date')

    if not retailer or not crawl_date:
        return JsonResponse({'error': '리테일러와 날짜가 필요합니다.'}, status=400)

    try:
        result = screenshot_services.get_screenshot_status(retailer, crawl_date)
        return JsonResponse(result)
    except Exception as e:
        return safe_error(e, success=False)


@require_http_methods(["POST"])
def screenshot_delete(request):
    """스크린샷 삭제 API"""
    try:
        body = json.loads(request.body)
        result = screenshot_services.delete_screenshots(body.get('anomaly_ids', []))
        return JsonResponse(result)
    except Exception as e:
        return safe_error(e, success=False)


@require_http_methods(["POST"])
def screenshot_upload(request):
    """스크린샷 수동 업로드 API"""
    try:
        uploaded_file = request.FILES.get('file')
        anomaly_id = request.POST.get('anomaly_id')

        if not uploaded_file or not anomaly_id:
            return JsonResponse({'success': False, 'error': '파일과 anomaly_id가 필요합니다.'})

        result = screenshot_services.upload_screenshot(
            file_obj=uploaded_file,
            anomaly_id=anomaly_id,
            username=request.user.username if request.user.is_authenticated else ''
        )
        return JsonResponse(result)
    except Exception as e:
        return safe_error(e, success=False)
