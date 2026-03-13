"""
DS Layer 1 — 배치 로그 API
"""

from django.http import JsonResponse
from datetime import datetime, timedelta
from apps.common.db import get_ds_connection
from apps.common.response import safe_error, log_error
from apps.common.targets import load_monitoring_targets_with_local_time, format_time
import json


def get_batches_for_date(target_date):
    """특정 날짜의 배치 목록을 리테일러별로 그룹화하여 반환"""
    batches_by_retailer = {}

    try:
        conn = get_ds_connection()
        cursor = conn.cursor()

        query = """
            SELECT id, retailer, start_time, memo
            FROM ssd_crawl_db.ds_collection_batch_log
            WHERE date = %s
            ORDER BY retailer, start_time
        """
        cursor.execute(query, (target_date,))
        rows = cursor.fetchall()

        for row in rows:
            retailer = row[1]
            if retailer not in batches_by_retailer:
                batches_by_retailer[retailer] = []

            batches_by_retailer[retailer].append({
                'id': row[0],
                'start_time': format_time(row[2]) if row[2] else '00:00',
                'memo': row[3]
            })

        cursor.close()
        conn.close()
    except Exception as e:
        print(f"Error loading batches: {e}")

    return batches_by_retailer


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
        conn = get_ds_connection()
        cursor = conn.cursor()

        # 해당 날짜의 배치 로그 조회
        query = """
            SELECT id, date, retailer, start_time, memo, created_at
            FROM ssd_crawl_db.ds_collection_batch_log
            WHERE date = %s
            ORDER BY retailer, start_time
        """
        cursor.execute(query, (target_date,))
        rows = cursor.fetchall()

        batches = []
        for row in rows:
            batches.append({
                'id': row[0],
                'date': str(row[1]),
                'retailer': row[2],
                'start_time': format_time(row[3]) if row[3] else None,
                'memo': row[4],
                'created_at': row[5].isoformat() if row[5] else None
            })

        cursor.close()
        conn.close()

        data['batches'] = batches

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
        conn = get_ds_connection()
        cursor = conn.cursor()

        # 이미 해당 날짜에 배치가 있는지 확인
        check_query = """
            SELECT COUNT(*) FROM ssd_crawl_db.ds_collection_batch_log
            WHERE date = %s
        """
        cursor.execute(check_query, (target_date,))
        count = cursor.fetchone()[0]

        if count > 0:
            cursor.close()
            conn.close()
            return JsonResponse({'message': '이미 배치가 존재합니다.', 'created': 0})

        # 모니터링 대상 목록에서 기본 배치 생성 (local_time 사용)
        targets = load_monitoring_targets_with_local_time()
        insert_query = """
            INSERT INTO ssd_crawl_db.ds_collection_batch_log
            (date, retailer, start_time, memo)
            VALUES (%s, %s, %s, %s)
        """

        created_count = 0
        for table_name, retailer, region, korea_time, local_time, country, mall_name in targets:
            cursor.execute(insert_query, (target_date, retailer, local_time + ':00', None))
            created_count += 1

        conn.commit()
        cursor.close()
        conn.close()

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
        conn = get_ds_connection()
        cursor = conn.cursor()

        insert_query = """
            INSERT INTO ssd_crawl_db.ds_collection_batch_log
            (date, retailer, start_time, memo)
            VALUES (%s, %s, %s, %s)
        """
        cursor.execute(insert_query, (date_str, retailer, start_time, memo))
        conn.commit()

        # 새로 생성된 ID 가져오기
        cursor.execute("SELECT LAST_INSERT_ID()")
        new_id = cursor.fetchone()[0]

        cursor.close()
        conn.close()

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
        conn = get_ds_connection()
        cursor = conn.cursor()

        # 업데이트할 필드 동적 구성
        updates = []
        params = []

        if start_time is not None:
            updates.append("start_time = %s")
            params.append(start_time)

        if memo is not None:
            updates.append("memo = %s")
            params.append(memo)

        if not updates:
            return JsonResponse({'error': '수정할 필드가 없습니다.'}, status=400)

        params.append(batch_id)

        update_query = f"""
            UPDATE ssd_crawl_db.ds_collection_batch_log
            SET {', '.join(updates)}
            WHERE id = %s
        """
        cursor.execute(update_query, params)
        conn.commit()

        affected = cursor.rowcount
        cursor.close()
        conn.close()

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
        conn = get_ds_connection()
        cursor = conn.cursor()

        delete_query = """
            DELETE FROM ssd_crawl_db.ds_collection_batch_log
            WHERE id = %s
        """
        cursor.execute(delete_query, (batch_id,))
        conn.commit()

        affected = cursor.rowcount
        cursor.close()
        conn.close()

        if affected == 0:
            return JsonResponse({'error': '해당 배치를 찾을 수 없습니다.'}, status=404)

        return JsonResponse({'message': '배치가 삭제되었습니다.'})

    except Exception as e:
        return safe_error(e)
