"""
DS Layer 3 Stats API: HTTP 요청/응답 처리 컨트롤러
"""
from datetime import datetime, timedelta
from django.http import JsonResponse
from apps.common.response import safe_error
from . import stats_services

def layer_stats(request):
    """SKU 이상치 요약 통계 API"""
    date_str = request.GET.get('date')
    try:
        days = max(1, min(int(request.GET.get('days', 7)), 30))
    except (ValueError, TypeError):
        days = 7

    if date_str:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    else:
        target_date = (datetime.now() - timedelta(days=1)).date()

    data = stats_services.get_layer_stats(target_date, days)
    return JsonResponse(data)

def sku_detail(request):
    """특정 리테일러 SKU 이상치 상세 API"""
    date_str = request.GET.get('date')
    retailer = request.GET.get('retailer')
    filter_type = request.GET.get('filter', 'all')
    sort_by = request.GET.get('sort_by', 'consecutive_days')
    sort_order = request.GET.get('sort_order', 'desc')

    try:
        days = max(1, min(int(request.GET.get('days', 7)), 30))
        page = max(1, int(request.GET.get('page', 1)))
        page_size = min(int(request.GET.get('page_size', 50)), 200)
    except (ValueError, TypeError):
        return JsonResponse({'error': '잘못된 파라미터'}, status=400)

    if not retailer:
        return JsonResponse({'error': '리테일러를 지정하세요.'}, status=400)

    if filter_type not in ('all', 'new', 'repeat'):
        filter_type = 'all'

    if sort_by not in ('consecutive_days', 'retailersku', 'total_appearances'):
        sort_by = 'consecutive_days'

    if date_str:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    else:
        target_date = (datetime.now() - timedelta(days=1)).date()

    data = stats_services.get_sku_detail(target_date, days, retailer, filter_type, sort_by, sort_order, page, page_size)
    return JsonResponse(data)

def sku_history(request):
    """단일 SKU 이력 API"""
    date_str = request.GET.get('date')
    retailer = request.GET.get('retailer')
    retailersku = request.GET.get('retailersku')

    try:
        days = max(1, min(int(request.GET.get('days', 7)), 30))
    except (ValueError, TypeError):
        days = 7

    if not retailer or not retailersku:
        return JsonResponse({'error': '리테일러와 SKU를 지정하세요.'}, status=400)

    if date_str:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    else:
        target_date = (datetime.now() - timedelta(days=1)).date()

    data = stats_services.get_sku_history(target_date, days, retailer, retailersku)
    return JsonResponse(data)
