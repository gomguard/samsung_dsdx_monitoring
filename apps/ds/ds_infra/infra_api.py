"""
인프라 모니터링 API: HTTP 요청/응답 처리
"""

import json
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST
from . import infra_services


@require_GET
def ec2_status(request):
    """EC2 인스턴스 상태 조회 API"""
    result = infra_services.get_ec2_status()
    return JsonResponse({'success': True, 'instances': result})


@require_POST
def ec2_action(request):
    """EC2 인스턴스 시작/종료 API"""
    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'success': False, 'message': 'Invalid JSON'}, status=400)

    result = infra_services.perform_ec2_action(
        key=body.get('key'),
        action=body.get('action'),
        username=request.user.username if request.user.is_authenticated else 'system'
    )
    
    response = {'success': result['success']}
    if result.get('message'):
        response['message'] = result['message']
    return JsonResponse(response, status=result['status'])
