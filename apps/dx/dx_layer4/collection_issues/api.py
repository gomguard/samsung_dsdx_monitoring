"""
Layer 4 수집 이슈 API — 목록 조회, 저장, 삭제, 정상처리
"""

import json
from datetime import datetime
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from apps.common.db import get_dx_connection
from apps.common.response import safe_error


def collection_issues_list(request):
    """수집 이슈 목록 조회 (GET)"""
    date_str = request.GET.get('date')
    section = request.GET.get('section', '')

    if not date_str:
        return JsonResponse({'success': False, 'error': '날짜를 지정하세요.'}, status=400)

    conn = get_dx_connection()
    cursor = conn.cursor()
    try:
        sql = """
            SELECT id, crawl_date, section, title, issue_date,
                   symptom, cause, action, created_id, created_at,
                   resolution_status, resolved_at, resolved_id, resolution_memo
            FROM monitoring_check_log_issues
            WHERE crawl_date = %s AND is_del = 0
        """
        params = [date_str]
        if section:
            sql += " AND section = %s"
            params.append(section)
        sql += " ORDER BY id"

        cursor.execute(sql, params)
        items = []
        for row in cursor.fetchall():
            items.append({
                'id': row[0],
                'crawl_date': str(row[1]),
                'section': row[2],
                'title': row[3],
                'issue_date': row[4] or '',
                'symptom': row[5] or '',
                'cause': row[6] or '',
                'action': row[7] or '',
                'created_id': row[8] or '',
                'created_at': row[9].isoformat() if row[9] else None,
                'resolution_status': row[10] or 'open',
                'resolved_at': row[11].isoformat() if row[11] else None,
                'resolved_id': row[12] or '',
                'resolution_memo': row[13] or '',
            })

        return JsonResponse({'success': True, 'items': items})
    except Exception as e:
        return safe_error(e, 'collection_issues_list')
    finally:
        cursor.close()
        conn.close()


@require_POST
def collection_issue_save(request):
    """수집 이슈 저장 (INSERT or UPDATE)"""
    try:
        data = json.loads(request.body)
        issue_id = data.get('id')
        detail_id = data.get('detail_id')
        crawl_date = data.get('crawl_date')
        section = data.get('section', '')
        title = data.get('title', '')
        issue_date = data.get('issue_date', '')
        symptom = data.get('symptom', '')
        cause = data.get('cause', '')
        action = data.get('action', '')
        already_resolved = data.get('already_resolved', False)
        username = request.user.username if request.user.is_authenticated else ''
        now = datetime.now()

        if not crawl_date or not title:
            return JsonResponse({'success': False, 'error': '날짜와 제목은 필수입니다.'}, status=400)

        conn = get_dx_connection()
        cursor = conn.cursor()
        try:
            if issue_id:
                cursor.execute("""
                    UPDATE monitoring_check_log_issues
                    SET title = %s, issue_date = %s, symptom = %s,
                        cause = %s, action = %s, updated_id = %s, updated_at = %s
                    WHERE id = %s
                """, (title, issue_date, symptom, cause, action, username, now, issue_id))
                conn.commit()
                return JsonResponse({'success': True, 'id': issue_id})
            else:
                if already_resolved:
                    cursor.execute("""
                        INSERT INTO monitoring_check_log_issues
                            (crawl_date, section, title, issue_date, symptom, cause, action,
                             resolution_status, resolved_at, resolved_id,
                             created_id, created_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s,
                                'resolved', %s, %s,
                                %s, %s)
                        RETURNING id
                    """, (crawl_date, section, title, issue_date, symptom, cause, action,
                          now, username,
                          username, now))
                else:
                    cursor.execute("""
                        INSERT INTO monitoring_check_log_issues
                            (crawl_date, section, title, issue_date, symptom, cause, action,
                             created_id, created_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        RETURNING id
                    """, (crawl_date, section, title, issue_date, symptom, cause, action,
                          username, now))
                new_id = cursor.fetchone()[0]

                # detail 테이블에 issue_id 연결
                if detail_id:
                    cursor.execute("""
                        UPDATE monitoring_check_log_detail
                        SET issue_id = %s
                        WHERE id = %s
                    """, (new_id, detail_id))

                conn.commit()
                return JsonResponse({'success': True, 'id': new_id})
        finally:
            cursor.close()
            conn.close()
    except Exception as e:
        return safe_error(e, 'collection_issue_save')


@require_POST
def collection_issue_delete(request):
    """수집 이슈 삭제 (soft delete)"""
    try:
        data = json.loads(request.body)
        issue_id = data.get('id')
        if not issue_id:
            return JsonResponse({'success': False, 'error': 'id가 필요합니다.'}, status=400)

        username = request.user.username if request.user.is_authenticated else ''
        now = datetime.now()

        conn = get_dx_connection()
        cursor = conn.cursor()
        try:
            # soft delete
            cursor.execute("""
                UPDATE monitoring_check_log_issues
                SET is_del = 1, updated_id = %s, updated_at = %s
                WHERE id = %s
            """, (username, now, issue_id))

            # detail 테이블의 issue_id NULL 처리
            cursor.execute("""
                UPDATE monitoring_check_log_detail
                SET issue_id = NULL
                WHERE issue_id = %s
            """, (issue_id,))

            conn.commit()
            return JsonResponse({'success': True})
        finally:
            cursor.close()
            conn.close()
    except Exception as e:
        return safe_error(e, 'collection_issue_delete')


@require_POST
def collection_issue_resolve(request):
    """수집 이슈 정상처리"""
    try:
        data = json.loads(request.body)
        issue_id = data.get('id')
        resolution_memo = data.get('resolution_memo', '')

        if not issue_id:
            return JsonResponse({'success': False, 'error': 'id가 필요합니다.'}, status=400)

        username = request.user.username if request.user.is_authenticated else ''
        now = datetime.now()

        conn = get_dx_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                UPDATE monitoring_check_log_issues
                SET resolution_status = 'resolved', resolved_at = %s,
                    resolved_id = %s, resolution_memo = %s,
                    updated_id = %s, updated_at = %s
                WHERE id = %s AND is_del = 0
            """, (now, username, resolution_memo, username, now, issue_id))
            conn.commit()
            return JsonResponse({'success': True, 'id': issue_id})
        finally:
            cursor.close()
            conn.close()
    except Exception as e:
        return safe_error(e, 'collection_issue_resolve')
