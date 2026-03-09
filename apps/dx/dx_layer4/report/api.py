"""
Layer 4 보고서 API — 보고서 데이터 조회
"""

from django.http import JsonResponse
from apps.common.db import get_dx_connection
from apps.common.response import safe_error
from apps.common.params import parse_date


def report_data(request):
    """보고서 데이터 조회 (GET)"""
    target_date = parse_date(request.GET.get('date'))
    if target_date is None:
        return JsonResponse({'error': '날짜 형식이 올바르지 않습니다.'}, status=400)

    conn = None
    try:
        conn = get_dx_connection()
        cursor = conn.cursor()

        # 수집현황 (monitoring_check_log)
        cursor.execute("""
            SELECT section, expected_count, actual_count, rate, status, memo
            FROM monitoring_check_log
            WHERE crawl_date = %s AND layer = 1 AND is_del = 0 AND confirm_step = 2
            ORDER BY id
        """, (str(target_date),))
        collection_status = []
        for row in cursor.fetchall():
            collection_status.append({
                'section': row[0],
                'expected': row[1] or 0,
                'actual': row[2] or 0,
                'rate': float(row[3]) if row[3] else 0,
                'status': row[4] or '',
                'memo': row[5] or '',
            })

        # 수집 이슈
        cursor.execute("""
            SELECT id, section, title, issue_date, symptom, cause, action,
                   resolution_status, resolution_memo
            FROM monitoring_check_log_issues
            WHERE crawl_date = %s AND is_del = 0
            ORDER BY section, id
        """, (str(target_date),))
        collection_issues = []
        for row in cursor.fetchall():
            collection_issues.append({
                'id': row[0],
                'section': row[1],
                'title': row[2],
                'issue_date': row[3] or '',
                'symptom': row[4] or '',
                'cause': row[5] or '',
                'action': row[6] or '',
                'resolution_status': row[7] or 'open',
                'resolution_memo': row[8] or '',
            })

        # 검증유형별 수정/정상처리 요약
        cursor.execute("""
            SELECT correction_type, status, COUNT(*) as cnt
            FROM monitoring_corrections
            WHERE crawl_date = %s AND status IS NOT NULL
            GROUP BY correction_type, status
            ORDER BY correction_type, status
        """, (str(target_date),))
        type_summary = {}
        for row in cursor.fetchall():
            ct = row[0]
            if ct not in type_summary:
                type_summary[ct] = {}
            type_summary[ct][row[1]] = row[2]

        # 원인별 정상처리 건수
        cursor.execute("""
            SELECT reason, correction_type, COUNT(*) as cnt
            FROM monitoring_corrections
            WHERE crawl_date = %s AND status = 'normal'
            GROUP BY reason, correction_type
            ORDER BY cnt DESC
        """, (str(target_date),))
        reason_summary = []
        for row in cursor.fetchall():
            reason_summary.append({
                'reason': row[0] or '미지정',
                'correction_type': row[1],
                'count': row[2],
            })

        # 테이블별 수정 현황
        cursor.execute("""
            SELECT table_name, correction_type, status, COUNT(*) as cnt
            FROM monitoring_corrections
            WHERE crawl_date = %s AND status IS NOT NULL
            GROUP BY table_name, correction_type, status
            ORDER BY table_name, correction_type
        """, (str(target_date),))
        table_summary = {}
        for row in cursor.fetchall():
            tn = row[0]
            if tn not in table_summary:
                table_summary[tn] = {}
            ct = row[1]
            if ct not in table_summary[tn]:
                table_summary[tn][ct] = {}
            table_summary[tn][ct][row[2]] = row[3]

        # 수정 상세 목록 (보고서용)
        cursor.execute("""
            SELECT c.correction_type, c.table_name, c.column_name,
                   c.record_id, c.old_value, c.new_value, c.status, c.memo,
                   c.reason, c.created_id, c.retailer, c.item,
                   c.rule_id, r.detail_name, r.detail_code
            FROM monitoring_corrections c
            LEFT JOIN monitoring_validation_rules r ON c.rule_id = r.id
            WHERE c.crawl_date = %s AND c.status IN ('corrected', 'normal')
            ORDER BY c.correction_type, c.table_name, c.created_at
        """, (str(target_date),))
        details = []
        for row in cursor.fetchall():
            details.append({
                'correction_type': row[0],
                'table_name': row[1],
                'column_name': row[2],
                'record_id': row[3],
                'old_value': row[4],
                'new_value': row[5],
                'status': row[6],
                'memo': row[7] or '',
                'reason': row[8] or '',
                'created_id': row[9] or '',
                'retailer': row[10] or '',
                'item': row[11] or '',
                'rule_id': row[12],
                'rule_name': row[13] or '',
                'detail_code': row[14] or '',
            })

        # correction_type → table_name 그룹핑
        grouped_details = {}
        for d in details:
            ct = d['correction_type']
            tn = d['table_name']
            if ct not in grouped_details:
                grouped_details[ct] = {}
            if tn not in grouped_details[ct]:
                grouped_details[ct][tn] = []
            grouped_details[ct][tn].append(d)

        # 비제품 제외 (is_product: true → false 변경 이력)
        cursor.execute("""
            SELECT h.table_name, h.item_id,
                   CASE WHEN h.table_name = 'tv_item_mst' THEN m_tv.account_name
                        WHEN h.table_name = 'hhp_item_mst' THEN m_hhp.account_name
                        ELSE NULL END as account_name,
                   CASE WHEN h.table_name = 'tv_item_mst' THEN m_tv.item
                        WHEN h.table_name = 'hhp_item_mst' THEN m_hhp.item
                        ELSE NULL END as item
            FROM item_mst_history h
            LEFT JOIN tv_item_mst m_tv ON h.table_name = 'tv_item_mst' AND h.item_id = m_tv.id
            LEFT JOIN hhp_item_mst m_hhp ON h.table_name = 'hhp_item_mst' AND h.item_id = m_hhp.id
            WHERE h.field_name = 'is_product'
              AND h.old_value = 'True' AND h.new_value = 'False'
              AND DATE(h.changed_at) = DATE(%s) + INTERVAL '1 day'
            ORDER BY h.table_name, h.changed_at
        """, (str(target_date),))
        excluded_items = []
        for row in cursor.fetchall():
            table_name_h = row[0]
            category = 'TV' if table_name_h == 'tv_item_mst' else 'HHP'
            account_name = row[2] or ''
            item_code = row[3] or ''
            excluded_items.append({
                'category': category,
                'account_name': account_name,
                'item': item_code,
            })

        # 수요증감율 부족 키워드
        cursor.execute("""
            SELECT k.event_name, k.category, k.product_name, k.event_date
            FROM monitoring_check_log_keywords k
            JOIN monitoring_check_log cl ON k.check_log_id = cl.id
            WHERE cl.crawl_date = %s AND cl.section = 'market_demand' AND cl.is_del = 0
            ORDER BY k.event_name, k.category, k.product_name
        """, (str(target_date),))
        missing_keywords = []
        for row in cursor.fetchall():
            missing_keywords.append({
                'event_name': row[0],
                'category': row[1],
                'product_name': row[2],
                'event_date': str(row[3]) if row[3] else '',
            })

        cursor.close()
        conn.close()

        return JsonResponse({
            'success': True,
            'date': str(target_date),
            'collection_status': collection_status,
            'collection_issues': collection_issues,
            'missing_keywords': missing_keywords,
            'type_summary': type_summary,
            'reason_summary': reason_summary,
            'table_summary': table_summary,
            'details': details,
            'grouped_details': grouped_details,
            'excluded_items': excluded_items,
        })
    except Exception as e:
        if conn:
            try:
                conn.close()
            except Exception:
                pass
        return safe_error(e)
