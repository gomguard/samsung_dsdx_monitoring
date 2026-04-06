from django.http import JsonResponse
from datetime import datetime, timedelta
from apps.common.response import log_error
from . import market_promotion_services as svc


def market_promotion_raw_data(request):
    """Market Promotion Raw Data API"""
    date_str = request.GET.get('date')
    retailer = request.GET.get('retailer', '')

    if date_str:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    else:
        target_date = (datetime.now() - timedelta(days=1)).date()

    try:
        result = svc.get_promotion_raw_data(retailer, target_date)
        return JsonResponse(result)
    except Exception as e:
        return JsonResponse({'error': log_error(e)})
