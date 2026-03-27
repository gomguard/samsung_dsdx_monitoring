"""
Layer 4 수집 이슈 Services — 목록 조회, 저장, 삭제, 정상처리
"""

from datetime import datetime
from apps.common.db import dx_connection


def list_issues(date_str, section=''):
    """수집 이슈 목록 조회"""
    with dx_connection() as (conn, cursor):
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

    return {'success': True, 'items': items}


def save_issue(issue_id, detail_id, crawl_date, section, title, issue_date,
               symptom, cause, action, already_resolved, username):
    """수집 이슈 저장 (INSERT or UPDATE)"""
    now = datetime.now()
    with dx_connection() as (conn, cursor):
        if issue_id:
            if already_resolved:
                cursor.execute("""
                    UPDATE monitoring_check_log_issues
                    SET title = %s, issue_date = %s, symptom = %s,
                        cause = %s, action = %s, updated_id = %s, updated_at = %s,
                        resolution_status = 'resolved', resolved_at = %s, resolved_id = %s
                    WHERE id = %s
                """, (title, issue_date, symptom, cause, action, username, now,
                      now, username, issue_id))
            else:
                cursor.execute("""
                    UPDATE monitoring_check_log_issues
                    SET title = %s, issue_date = %s, symptom = %s,
                        cause = %s, action = %s, updated_id = %s, updated_at = %s,
                        resolution_status = 'open', resolved_at = NULL, resolved_id = NULL
                    WHERE id = %s
                """, (title, issue_date, symptom, cause, action, username, now, issue_id))
            return {'success': True, 'id': issue_id}
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
                      now, username, username, now))
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

            if detail_id:
                cursor.execute("""
                    UPDATE monitoring_check_log_detail
                    SET issue_id = %s
                    WHERE id = %s
                """, (new_id, detail_id))

            return {'success': True, 'id': new_id}


def delete_issue(issue_id, username):
    """수집 이슈 삭제 (soft delete)"""
    now = datetime.now()
    with dx_connection() as (conn, cursor):
        cursor.execute("""
            UPDATE monitoring_check_log_issues
            SET is_del = 1, updated_id = %s, updated_at = %s
            WHERE id = %s
        """, (username, now, issue_id))

        cursor.execute("""
            UPDATE monitoring_check_log_detail
            SET issue_id = NULL
            WHERE issue_id = %s
        """, (issue_id,))

    return {'success': True}


def resolve_issue(issue_id, resolution_memo, username):
    """수집 이슈 정상처리"""
    now = datetime.now()
    with dx_connection() as (conn, cursor):
        cursor.execute("""
            UPDATE monitoring_check_log_issues
            SET resolution_status = 'resolved', resolved_at = %s,
                resolved_id = %s, resolution_memo = %s,
                updated_id = %s, updated_at = %s
            WHERE id = %s AND is_del = 0
        """, (now, username, resolution_memo, username, now, issue_id))

    return {'success': True, 'id': issue_id}
