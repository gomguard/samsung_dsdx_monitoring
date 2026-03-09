"""
Layer 4 마감기록 API — 검수 이력 조회, 메모 수정
"""

import json
from datetime import datetime, timedelta
from django.http import JsonResponse
from apps.common.db import get_dx_connection
from apps.common.response import safe_error


ALL_SECTIONS = [
    'retail', 'sentiment', 'youtube', 'market_trend',
    'market_competitor', 'market_competitor_event',
    'market_demand', 'market_promotion',
]


def _get_target_sections(date_str):
    """해당 날짜의 검증 대상 섹션 수 계산"""
    from datetime import date as date_cls
    target_date = date_cls.fromisoformat(date_str)

    # 기본 대상: retail, sentiment, youtube, market_trend, market_demand (5개)
    count = 5

    # market_competitor: 분기 첫날
    if target_date.day == 1 and target_date.month in [1, 4, 7, 10]:
        count += 1

    # market_competitor_event: 매월 첫 월요일
    first_day = target_date.replace(day=1)
    days_until_monday = (7 - first_day.weekday()) % 7
    first_monday = first_day if first_day.weekday() == 0 else first_day + timedelta(days=days_until_monday)
    if target_date == first_monday:
        count += 1

    # market_promotion: 월요일
    if target_date.weekday() == 0:
        count += 1

    return count


def check_log_list(request):
    """단일 날짜 검수 이력 (활성 + 취소 포함)"""
    date_str = request.GET.get('date')
    layer = int(request.GET.get('layer', 1))

    if not date_str:
        return JsonResponse({'success': False, 'error': '날짜를 지정하세요.'}, status=400)

    conn = get_dx_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT id, section, expected_count, actual_count, rate, status, memo,
                   is_del, delete_memo, created_id, created_at, updated_id, updated_at,
                   confirm_step
            FROM monitoring_check_log
            WHERE crawl_date = %s AND layer = %s
            ORDER BY section, created_at DESC
        """, (date_str, layer))

        rows = cursor.fetchall()
        logs = []
        for row in rows:
            logs.append({
                'id': row[0],
                'section': row[1],
                'expected_count': row[2],
                'actual_count': row[3],
                'rate': float(row[4]) if row[4] else 0,
                'status': row[5],
                'memo': row[6] or '',
                'is_del': row[7],
                'delete_memo': row[8] or '',
                'created_id': row[9] or '',
                'created_at': row[10].isoformat() if row[10] else None,
                'updated_id': row[11] or '',
                'updated_at': row[12].isoformat() if row[12] else None,
                'confirm_step': row[13],
            })

        active_count = sum(1 for l in logs if l['is_del'] == 0)

        return JsonResponse({
            'success': True,
            'logs': logs,
            'active_count': active_count,
            'total_sections': _get_target_sections(date_str),
        })
    except Exception as e:
        return safe_error(e, 'db')
    finally:
        cursor.close()
        conn.close()


def check_memo_update(request):
    """검수 기록 메모 수정"""
    try:
        data = json.loads(request.body)
        log_id = data.get('id')
        memo = data.get('memo', '')
        username = request.user.username if request.user.is_authenticated else ''
        now = datetime.now()

        if not log_id:
            return JsonResponse({'success': False, 'error': 'id가 누락되었습니다.'}, status=400)

        conn = get_dx_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                UPDATE monitoring_check_log
                SET memo = %s, updated_id = %s, updated_at = %s
                WHERE id = %s AND is_del = 0
            """, (memo, username, now, log_id))
            conn.commit()
            return JsonResponse({'success': True, 'updated': cursor.rowcount})
        finally:
            cursor.close()
            conn.close()
    except Exception as e:
        return safe_error(e, 'memo_update')
