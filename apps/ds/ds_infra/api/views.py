"""
인프라 모니터링 API: HTTP 요청/응답 처리
"""

import json
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST
from .services import get_ec2_status, perform_ec2_action


@require_GET
def ec2_status(request):
    """EC2 인스턴스 상태 조회"""
    result = get_ec2_status()
    return JsonResponse({'success': True, 'instances': result})


@require_POST
def ec2_action(request):
    """EC2 인스턴스 시작/종료"""
    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'success': False}, status=400)

    result = perform_ec2_action(
        key=body.get('key'),
        action=body.get('action'),
        username=request.user.username
    )
    response = {'success': result['success']}
    if result.get('message'):
        response['message'] = result['message']
    return JsonResponse(response, status=result['status'])
