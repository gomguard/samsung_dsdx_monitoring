"""
DS Layer 1 — 배치 로그 API
request 파싱 + services 호출 + JsonResponse 반환
"""

from django.http import JsonResponse
from datetime import datetime, timedelta
from apps.common.db import ds_connection
from apps.common.response import safe_error, log_error
from . import services
import json


def batch_list(request):
    """배치 로그 목록 조회 API (해당 날짜)"""
    date_str = request.GET.get('date')

    if date_str:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    else:
        target_date = (datetime.now() - timedelta(days=1)).date()

    data = {
        'timestamp': datetime.now().isoformat(),
        'date': str(target_date),
        'batches': []
    }

    try:
        with ds_connection() as (conn, cursor):
            data['batches'] = services.get_batch_list(cursor, target_date)

    except Exception as e:
        data['error'] = log_error(e)

    return JsonResponse(data)


def batch_init(request):
    """배치 로그 초기화 API (해당 날짜에 기본 배치 생성)"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST 요청만 허용됩니다.'}, status=405)

    try:
        body = json.loads(request.body)
        date_str = body.get('date')
    except:
        date_str = request.POST.get('date')

    if not date_str:
        return JsonResponse({'error': '날짜를 입력하세요.'}, status=400)

    try:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        return JsonResponse({'error': '날짜 형식이 올바르지 않습니다.'}, status=400)

    try:
        with ds_connection() as (conn, cursor):
            created_count = services.init_batches(cursor, conn, target_date)

            if created_count == 0:
                return JsonResponse({'message': '이미 배치가 존재합니다.', 'created': 0})

            return JsonResponse({'message': f'{created_count}개 배치가 생성되었습니다.', 'created': created_count})

    except Exception as e:
        return safe_error(e)


def batch_create(request):
    """배치 로그 추가 API"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST 요청만 허용됩니다.'}, status=405)

    try:
        body = json.loads(request.body)
    except:
        return JsonResponse({'error': '잘못된 요청 형식입니다.'}, status=400)

    date_str = body.get('date')
    retailer = body.get('retailer')
    start_time = body.get('start_time')
    memo = body.get('memo', '')

    if not date_str or not retailer or not start_time:
        return JsonResponse({'error': '필수 필드가 누락되었습니다.'}, status=400)

    try:
        with ds_connection() as (conn, cursor):
            new_id = services.create_batch(cursor, conn, date_str, retailer, start_time, memo)

            return JsonResponse({'message': '배치가 추가되었습니다.', 'id': new_id})

    except Exception as e:
        return safe_error(e)


def batch_update(request):
    """배치 로그 수정 API"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST 요청만 허용됩니다.'}, status=405)

    try:
        body = json.loads(request.body)
    except:
        return JsonResponse({'error': '잘못된 요청 형식입니다.'}, status=400)

    batch_id = body.get('id')
    start_time = body.get('start_time')
    memo = body.get('memo')

    if not batch_id:
        return JsonResponse({'error': 'ID가 필요합니다.'}, status=400)

    try:
        with ds_connection() as (conn, cursor):
            affected = services.update_batch(cursor, conn, batch_id, start_time, memo)

            if affected == -1:
                return JsonResponse({'error': '수정할 필드가 없습니다.'}, status=400)

            if affected == 0:
                return JsonResponse({'error': '해당 배치를 찾을 수 없습니다.'}, status=404)

            return JsonResponse({'message': '배치가 수정되었습니다.'})

    except Exception as e:
        return safe_error(e)


def batch_delete(request):
    """배치 로그 삭제 API"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST 요청만 허용됩니다.'}, status=405)

    try:
        body = json.loads(request.body)
    except:
        return JsonResponse({'error': '잘못된 요청 형식입니다.'}, status=400)

    batch_id = body.get('id')

    if not batch_id:
        return JsonResponse({'error': 'ID가 필요합니다.'}, status=400)

    try:
        with ds_connection() as (conn, cursor):
            affected = services.delete_batch(cursor, conn, batch_id)

            if affected == 0:
                return JsonResponse({'error': '해당 배치를 찾을 수 없습니다.'}, status=404)

            return JsonResponse({'message': '배치가 삭제되었습니다.'})

    except Exception as e:
        return safe_error(e)
