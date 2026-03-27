"""
Layer 4 마감기록 API — 검수 이력 조회, 메모 수정
"""

import json
from django.http import JsonResponse
from apps.common.response import safe_error
from .services import get_check_log_list, update_check_memo, get_check_status


def check_status(request):
    """날짜별 검수 확인 상태 조회 (운영 테이블)"""
    date_str = request.GET.get('date')
    layer = int(request.GET.get('layer', 1))
    include_detail = request.GET.get('detail', '0') == '1'

    if not date_str:
        return JsonResponse({'success': False, 'error': '날짜를 지정하세요.'}, status=400)

    try:
        return JsonResponse(get_check_status(date_str, layer, include_detail))
    except Exception as e:
        return safe_error(e, 'db')


def check_log_list(request):
    """단일 날짜 검수 이력 (활성 + 취소 포함)"""
    date_str = request.GET.get('date')
    layer = int(request.GET.get('layer', 1))

    if not date_str:
        return JsonResponse({'success': False, 'error': '날짜를 지정하세요.'}, status=400)

    try:
        return JsonResponse(get_check_log_list(date_str, layer))
    except Exception as e:
        return safe_error(e, 'db')


def check_memo_update(request):
    """검수 기록 메모 수정"""
    try:
        data = json.loads(request.body)
        log_id = data.get('id')
        memo = data.get('memo', '')
        username = request.user.username if request.user.is_authenticated else ''

        if not log_id:
            return JsonResponse({'success': False, 'error': 'id가 누락되었습니다.'}, status=400)

        return JsonResponse(update_check_memo(log_id, memo, username))
    except Exception as e:
        return safe_error(e, 'memo_update')
