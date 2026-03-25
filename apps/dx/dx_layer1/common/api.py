"""
검수 확인/완료 API (HTTP 래핑)
"""

from django.http import JsonResponse
from django.views.decorators.http import require_POST
import json
from apps.common.db import dx_connection
from apps.common.response import safe_error
from apps.dx.dx_layer1.common import services


def check_status(request):
    """날짜별 검수 확인 상태 조회"""
    date_str = request.GET.get('date')
    layer = int(request.GET.get('layer', 1))
    include_detail = request.GET.get('detail', '0') == '1'

    if not date_str:
        return JsonResponse({'success': False, 'error': '날짜를 지정하세요.'}, status=400)

    try:
        with dx_connection() as (conn, cursor):
            result = services.get_check_status(cursor, date_str, layer, include_detail)
            return JsonResponse(result)
    except Exception as e:
        return safe_error(e, 'db')


@require_POST
def check_save(request):
    """검수 확인 저장"""
    try:
        data = json.loads(request.body)
        date_str = data.get('date')
        layer = data.get('layer', 1)
        step = data.get('step', 1)
        sections = data.get('sections', [])
        username = request.user.username if request.user.is_authenticated else ''

        if not date_str or not sections:
            return JsonResponse({'success': False, 'error': '필수 파라미터가 누락되었습니다.'}, status=400)

        with dx_connection() as (conn, cursor):
            result = services.save_check(cursor, conn, date_str, layer, step, sections, username)
            if not result['success']:
                return JsonResponse(result, status=400)
            return JsonResponse(result)
    except Exception as e:
        return safe_error(e, 'save')


@require_POST
def check_delete(request):
    """검수 확인 취소"""
    try:
        data = json.loads(request.body)
        date_str = data.get('date')
        section = data.get('section')
        layer = data.get('layer', 1)
        step = data.get('step', 0)
        delete_memo = data.get('delete_memo', '')
        username = request.user.username if request.user.is_authenticated else ''

        if not date_str:
            return JsonResponse({'success': False, 'error': '날짜를 지정하세요.'}, status=400)

        with dx_connection() as (conn, cursor):
            result = services.delete_check(cursor, conn, date_str, layer, section, step, delete_memo, username)
            return JsonResponse(result)
    except Exception as e:
        return safe_error(e, 'delete')
