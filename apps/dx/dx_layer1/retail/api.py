from django.http import JsonResponse
from datetime import datetime, timedelta
from apps.common.db import dx_connection
from apps.common.response import log_error
from . import services


def retail_detail(request):
    """리테일 상세 현황 API"""
    date_str = request.GET.get('date')
    product_line = request.GET.get('type', 'tv')  # tv or hhp

    if date_str:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    else:
        target_date = (datetime.now() - timedelta(days=1)).date()

    try:
        with dx_connection() as (conn, cursor):
            result = services.get_retail_detail(cursor, target_date, product_line)
            return JsonResponse(result)
    except Exception as e:
        return JsonResponse({'error': log_error(e)})


def retail_summary(request):
    """Retail 상세 현황 API - 리테일러×시간대×페이지타입별 테이블 + NULL 컬럼 현황"""
    date_str = request.GET.get('date')
    product_line = request.GET.get('type', 'tv')  # tv or hhp

    if date_str:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    else:
        target_date = (datetime.now() - timedelta(days=1)).date()

    try:
        with dx_connection() as (conn, cursor):
            result = services.get_retail_summary(cursor, target_date, product_line)
            return JsonResponse(result)
    except Exception as e:
        return JsonResponse({'error': log_error(e)})


def retailer_raw_data(request):
    """
    리테일러별 원본 데이터 조회 API
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
        with dx_connection() as (conn, cursor):
            result = services.get_retailer_raw_data(cursor, category, retailer, period, target_date)
            return JsonResponse(result)
    except Exception as e:
        return JsonResponse({'error': log_error(e)})


def retailer_columns_info(request):
    """
    TV/HHP 리테일러별 수집 컬럼 정보 API
    - DB(monitoring_retail_columns)에서 컬럼 정보 로드
    """
    try:
        result = services.get_retailer_columns_info()
        return JsonResponse(result)
    except Exception as e:
        return JsonResponse({'error': log_error(e)})


def backup_status(request):
    """백업 상태 확인 API — Layer 2/3 진입 시 호출"""
    from apps.common.backup import get_backup_status

    target_date = request.GET.get('date', '').strip()
    if not target_date:
        return JsonResponse({'success': True, 'pending_count': 0, 'has_backup': True})

    return JsonResponse(get_backup_status(target_date))


def backup_retail_data(request):
    """TV/HHP retail 데이터 백업 API
    GET: 백업 대상 건수 조회
    POST: 백업 실행
    """
    from apps.common.backup import backup_all_retail, get_backup_count

    target_date = request.GET.get('date') or request.POST.get('date') or ''
    target_date = target_date.strip() or None

    if request.method == 'GET':
        # 건수만 조회
        result = get_backup_count(target_date)
        if result['success']:
            return JsonResponse({
                'success': True,
                'tv_count': result['tv_count'],
                'hhp_count': result['hhp_count'],
                'total_count': result['total_count']
            })
        else:
            return JsonResponse({'success': False, 'error': result.get('error', 'Unknown error')})

    elif request.method == 'POST':
        # 백업 실행
        username = request.user.username if request.user.is_authenticated else ''
        result = backup_all_retail(username, target_date)

        if result['success']:
            tv_count = result['tv']['count']
            hhp_count = result['hhp']['count']
            message = f"백업 완료 - TV: {tv_count}건, HHP: {hhp_count}건"
            return JsonResponse({
                'success': True,
                'message': message,
                'tv_count': tv_count,
                'hhp_count': hhp_count
            })
        else:
            errors = []
            if not result['tv']['success']:
                errors.append(f"TV: {result['tv'].get('error', 'Unknown error')}")
            if not result['hhp']['success']:
                errors.append(f"HHP: {result['hhp'].get('error', 'Unknown error')}")
            return JsonResponse({
                'success': False,
                'error': ', '.join(errors)
            })
