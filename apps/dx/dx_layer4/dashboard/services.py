"""
Layer 4 대시보드 Services — 통계 조회
"""

from apps.common.db import dx_connection


def get_dashboard_stats(target_date):
    """대시보드 통계 조회"""
    with dx_connection() as (conn, cursor):
        cursor.execute("""
            SELECT status, COUNT(*) as cnt
            FROM monitoring_corrections
            WHERE crawl_date = %s AND status IS NOT NULL
            GROUP BY status
        """, (str(target_date),))
        status_counts = {}
        for row in cursor.fetchall():
            status_counts[row[0]] = row[1]

        cursor.execute("""
            SELECT correction_type, status, COUNT(*) as cnt
            FROM monitoring_corrections
            WHERE crawl_date = %s AND status IS NOT NULL
            GROUP BY correction_type, status
        """, (str(target_date),))
        type_counts = {}
        for row in cursor.fetchall():
            ct = row[0]
            if ct not in type_counts:
                type_counts[ct] = {}
            type_counts[ct][row[1]] = row[2]

        cursor.execute("""
            SELECT reason, COUNT(*) as cnt
            FROM monitoring_corrections
            WHERE crawl_date = %s AND status = 'normal'
            GROUP BY reason
            ORDER BY cnt DESC
        """, (str(target_date),))
        reason_counts = [{'reason': row[0] or '미지정', 'count': row[1]} for row in cursor.fetchall()]

        cursor.execute("""
            SELECT table_name, status, COUNT(*) as cnt
            FROM monitoring_corrections
            WHERE crawl_date = %s AND status IS NOT NULL
            GROUP BY table_name, status
        """, (str(target_date),))
        table_counts = {}
        for row in cursor.fetchall():
            tn = row[0]
            if tn not in table_counts:
                table_counts[tn] = {}
            table_counts[tn][row[1]] = row[2]

    total = sum(status_counts.values())
    return {
        'success': True,
        'date': str(target_date),
        'total': total,
        'corrected': status_counts.get('corrected', 0),
        'normal': status_counts.get('normal', 0),
        'reverted': status_counts.get('reverted', 0),
        'by_type': type_counts,
        'by_reason': reason_counts,
        'by_table': table_counts,
    }
