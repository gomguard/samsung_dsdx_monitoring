from django.http import JsonResponse
from datetime import datetime, timedelta
from apps.common.response import log_error
from . import sentiment_services as svc


def sentiment_stats(request):
    """감성 분석 통계 API - 분석 대상 vs 저장된 결과"""
    date_str = request.GET.get('date')
    today = datetime.now().date()

    if date_str:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    else:
        target_date = today - timedelta(days=1)

    try:
        result = svc.get_sentiment_stats(target_date)
        return JsonResponse(result)
    except Exception as e:
        return JsonResponse({'error': log_error(e)})


def sentiment_raw_data(request):
    """
    감성분석 원본 데이터 조회 API
    - category: TV 또는 HHP
    - retailer: Amazon, Bestbuy, Walmart
    - period: 오전 또는 오후
    - date: 조회 날짜 (YYYY-MM-DD)
    """
    category = request.GET.get('category', 'TV')
    retailer = request.GET.get('retailer', 'Amazon')
    period = request.GET.get('period', '오전')
    date_str = request.GET.get('date')

    if not date_str:
        target_date = (datetime.now() - timedelta(days=1)).date()
    else:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()

    try:
        result = svc.get_sentiment_raw_data(category, retailer, period, target_date)
        return JsonResponse(result)
    except Exception as e:
        return JsonResponse({'error': log_error(e)})
