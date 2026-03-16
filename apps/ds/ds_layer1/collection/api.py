"""
DS Layer 1 - 수집 현황 API
request 파싱 + services 호출 + JsonResponse 반환
"""

from django.http import JsonResponse
from datetime import datetime, timedelta
from apps.common.db import ds_connection
from apps.common.response import log_error
from . import services


def layer_stats(request):
    """DS Layer 1 전체 통계 API"""
    date_str = request.GET.get('date')
    batch_view = request.GET.get('batch_view', 'final')

    if date_str:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    else:
        target_date = (datetime.now() - timedelta(days=1)).date()

    data = {
        'timestamp': datetime.now().isoformat(),
        'date': str(target_date),
        'layer': 1,
        'data_source': 'ds',
        'results': [],
        'summary': {}
    }

    try:
        with ds_connection() as (conn, cursor):
            result = services.get_layer_stats(cursor, target_date, batch_view, conn=conn)

            data['results'] = result['results']
            data['summary'] = result['summary']

    except Exception as e:
        data['error'] = log_error(e)
        data['summary'] = {
            'total_tables': len(services.get_monitoring_targets()),
            'total_expected': 0,
            'total_actual': 0,
            'total_completion_rate': 0,
            'status': 'error'
        }

    return JsonResponse(data)


def instances_stats(request):
    """인스턴스별(지역별) 그룹화된 통계 API"""
    date_str = request.GET.get('date')

    if date_str:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    else:
        target_date = (datetime.now() - timedelta(days=1)).date()

    data = {
        'timestamp': datetime.now().isoformat(),
        'date': str(target_date),
        'regions': {}
    }

    try:
        with ds_connection() as (conn, cursor):
            data['regions'] = services.get_instances_stats(cursor, target_date)

    except Exception as e:
        data['error'] = log_error(e)

    return JsonResponse(data)


def table_detail(request):
    """특정 테이블의 수집 데이터 상세 조회 API"""
    date_str = request.GET.get('date')
    table_name = request.GET.get('table')
    try:
        page = max(1, int(request.GET.get('page', 1)))
        page_size = min(int(request.GET.get('page_size', 50)), 200)
    except (ValueError, TypeError):
        return JsonResponse({'error': '잘못된 페이지 파라미터'}, status=400)
    start_time = request.GET.get('start_time')
    end_time = request.GET.get('end_time')
    sort_by = request.GET.get('sort_by', 'crawl_strdatetime')
    sort_order = request.GET.get('sort_order', 'asc')

    if not table_name:
        return JsonResponse({'error': '테이블명을 입력하세요.'})

    # 테이블명 검증
    valid_tables = [t[0] for t in services.get_monitoring_targets()]
    if table_name not in valid_tables:
        return JsonResponse({'error': '유효하지 않은 테이블명입니다.'})

    if date_str:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    else:
        target_date = (datetime.now() - timedelta(days=1)).date()

    data = {
        'timestamp': datetime.now().isoformat(),
        'date': str(target_date),
        'table': table_name,
        'page': page,
        'page_size': page_size,
        'start_time': start_time,
        'end_time': end_time,
        'sort_by': sort_by,
        'sort_order': sort_order,
        'data': []
    }

    try:
        with ds_connection() as (conn, cursor):
            result = services.get_table_detail(cursor, table_name, target_date, page, page_size, start_time, end_time, sort_by, sort_order)

            data.update(result)

    except Exception as e:
        data['error'] = log_error(e)

    return JsonResponse(data)
