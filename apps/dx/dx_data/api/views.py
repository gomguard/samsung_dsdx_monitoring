"""
DX 데이터 관리 API
- 아이템 마스터 조회/저장
- 변경 이력 조회
"""

import json
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from apps.common.response import safe_error
from apps.dx.dx_data.api.services import ALLOWED_TABLES, get_item_master_list, save_item_master, get_item_master_history


def item_master_list(request):
    """아이템 마스터 목록 조회"""
    table_key = request.GET.get('table', 'tv')
    if table_key not in ALLOWED_TABLES:
        return JsonResponse({'error': '잘못된 테이블'}, status=400)

    try:
        page = max(1, int(request.GET.get('page', 1)))
        page_size = min(int(request.GET.get('page_size', 50)), 200)
    except (ValueError, TypeError):
        return JsonResponse({'error': '잘못된 페이지 파라미터'}, status=400)

    try:
        result = get_item_master_list(
            table_key=table_key,
            is_product=request.GET.get('is_product', ''),
            is_checked=request.GET.get('is_checked', ''),
            account_name=request.GET.get('account_name', ''),
            search=request.GET.get('search', ''),
            search_field=request.GET.get('search_field', 'item'),
            page=page,
            page_size=page_size,
        )
        return JsonResponse(result)

    except Exception as e:
        return safe_error(e)


@require_POST
def item_master_save(request):
    """변경된 항목 일괄 저장 (is_product, is_checked 등)"""
    try:
        data = json.loads(request.body)
        table_key = data.get('table', 'tv')
        if table_key not in ALLOWED_TABLES:
            return JsonResponse({'error': '잘못된 테이블'}, status=400)

        changes = data.get('changes', [])
        if not changes:
            return JsonResponse({'error': '변경 항목 없음'}, status=400)

        user_id = request.user.username if request.user.is_authenticated else ''
        updated = save_item_master(table_key, changes, user_id)

        return JsonResponse({'success': True, 'updated': updated})

    except Exception as e:
        return safe_error(e, 'save')


def item_master_history(request):
    """변경 이력 조회"""
    table_key = request.GET.get('table', 'tv')
    if table_key not in ALLOWED_TABLES:
        return JsonResponse({'error': '잘못된 테이블'}, status=400)

    try:
        page = max(1, int(request.GET.get('page', 1)))
        page_size = min(int(request.GET.get('page_size', 50)), 200)
    except (ValueError, TypeError):
        return JsonResponse({'error': '잘못된 페이지 파라미터'}, status=400)

    try:
        result = get_item_master_history(
            table_key=table_key,
            date=request.GET.get('date', ''),
            field=request.GET.get('field', ''),
            account_name=request.GET.get('account_name', ''),
            item_search=request.GET.get('item', ''),
            page=page,
            page_size=page_size,
        )
        return JsonResponse(result)

    except Exception as e:
        return safe_error(e, 'db')
