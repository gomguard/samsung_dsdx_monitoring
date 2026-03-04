"""
Layer 4 API: 검수 확인 / 보고서 (Review & Report)
- 대시보드 통계
- 검수기록 목록
- 보고서 데이터
"""

from django.http import JsonResponse
from django.views.decorators.http import require_POST
from datetime import datetime, timedelta
import json
from apps.common.db import get_dx_connection
from apps.common.response import safe_error
from apps.common.params import parse_date


def dashboard_stats(request):
    """대시보드 통계 조회 (GET)"""
    target_date = parse_date(request.GET.get('date'))
    if target_date is None:
        return JsonResponse({'error': '날짜 형식이 올바르지 않습니다.'}, status=400)

    conn = None
    try:
        conn = get_dx_connection()
        cursor = conn.cursor()

        # 총 검수 건수 (status별)
        cursor.execute("""
            SELECT status, COUNT(*) as cnt
            FROM monitoring_corrections
            WHERE crawl_date = %s AND status IS NOT NULL
            GROUP BY status
        """, (str(target_date),))
        status_counts = {}
        for row in cursor.fetchall():
            status_counts[row[0]] = row[1]

        # correction_type별 건수
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

        # 원인별 건수 (정상 처리만)
        cursor.execute("""
            SELECT reason, COUNT(*) as cnt
            FROM monitoring_corrections
            WHERE crawl_date = %s AND status = 'normal'
            GROUP BY reason
            ORDER BY cnt DESC
        """, (str(target_date),))
        reason_counts = [{'reason': row[0] or '미지정', 'count': row[1]} for row in cursor.fetchall()]

        # 테이블별 건수
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

        cursor.close()
        conn.close()

        total = sum(status_counts.values())
        return JsonResponse({
            'success': True,
            'date': str(target_date),
            'total': total,
            'corrected': status_counts.get('corrected', 0),
            'normal': status_counts.get('normal', 0),
            'reverted': status_counts.get('reverted', 0),
            'by_type': type_counts,
            'by_reason': reason_counts,
            'by_table': table_counts,
        })
    except Exception as e:
        if conn:
            try:
                conn.close()
            except Exception:
                pass
        return safe_error(e)


def corrections_list(request):
    """검수기록 목록 조회 (GET)"""
    target_date = parse_date(request.GET.get('date'))
    if target_date is None:
        return JsonResponse({'error': '날짜 형식이 올바르지 않습니다.'}, status=400)

    correction_type = request.GET.get('type', 'all')
    status = request.GET.get('status', 'all')
    category = request.GET.get('category', 'all')
    rule_name = request.GET.get('rule_name', 'all')
    page = int(request.GET.get('page', 1))
    page_size = int(request.GET.get('page_size', 50))

    conn = None
    try:
        conn = get_dx_connection()
        cursor = conn.cursor()

        base_clauses = ["c.crawl_date = %s", "c.status IS NOT NULL"]
        base_params = [str(target_date)]

        if correction_type != 'all':
            base_clauses.append("c.correction_type = %s")
            base_params.append(correction_type)

        if category != 'all':
            category_table_map = {'TV': 'tv_retail_com', 'HHP': 'hhp_retail_com'}
            table_name = category_table_map.get(category)
            if table_name:
                base_clauses.append("c.table_name = %s")
                base_params.append(table_name)

        if rule_name != 'all':
            base_clauses.append("c.rule_id IN (SELECT id FROM monitoring_validation_rules WHERE detail_name = %s)")
            base_params.append(rule_name)

        # 탭 카운트 (status 필터 제외)
        base_where_sql = " AND ".join(base_clauses)
        cursor.execute(f"""
            SELECT c.status, COUNT(*) FROM monitoring_corrections c
            WHERE {base_where_sql}
            GROUP BY c.status
        """, base_params)
        status_counts = {}
        for row in cursor.fetchall():
            status_counts[row[0]] = row[1]

        # status 필터 적용
        where_clauses = list(base_clauses)
        params = list(base_params)
        if status != 'all':
            where_clauses.append("c.status = %s")
            params.append(status)

        where_sql = " AND ".join(where_clauses)

        # 총 건수
        cursor.execute(f"SELECT COUNT(*) FROM monitoring_corrections c WHERE {where_sql}", params)
        total_count = cursor.fetchone()[0]

        # 데이터 조회
        offset = (page - 1) * page_size
        cursor.execute(f"""
            SELECT c.id, c.layer, c.correction_type, c.table_name, c.record_id,
                   c.column_name, c.old_value, c.new_value, c.crawl_date,
                   c.status, c.memo, c.created_id, c.created_at, c.reason,
                   c.retailer, c.item, c.rule_id, r.detail_name,
                   c.updated_id, c.updated_at, c.cancel_memo
            FROM monitoring_corrections c
            LEFT JOIN monitoring_validation_rules r ON c.rule_id = r.id
            WHERE {where_sql}
            ORDER BY c.created_at DESC
            LIMIT %s OFFSET %s
        """, params + [page_size, offset])

        rows = cursor.fetchall()
        items = []
        for row in rows:
            items.append({
                'id': row[0],
                'layer': row[1],
                'correction_type': row[2],
                'table_name': row[3],
                'record_id': row[4],
                'column_name': row[5],
                'old_value': row[6],
                'new_value': row[7],
                'crawl_date': str(row[8]) if row[8] else '',
                'status': row[9],
                'memo': row[10] or '',
                'created_id': row[11] or '',
                'created_at': row[12].strftime('%Y-%m-%d %H:%M:%S') if row[12] else '',
                'reason': row[13] or '',
                'retailer': row[14] or '',
                'item': row[15] or '',
                'rule_id': row[16],
                'rule_name': row[17] or '',
                'updated_id': row[18] or '',
                'updated_at': row[19].strftime('%Y-%m-%d %H:%M:%S') if row[19] else '',
                'cancel_memo': row[20] or '',
            })

        # 크로스필드일 때 룰 목록 반환 (detail_name 기준 중복 제거)
        rule_options = []
        if correction_type == 'cross_field':
            cursor.execute("""
                SELECT DISTINCT r.detail_name
                FROM monitoring_corrections c
                LEFT JOIN monitoring_validation_rules r ON c.rule_id = r.id
                WHERE c.crawl_date = %s AND c.correction_type = 'cross_field'
                  AND c.status IS NOT NULL AND c.rule_id IS NOT NULL
                ORDER BY r.detail_name
            """, [str(target_date)])
            for rrow in cursor.fetchall():
                if rrow[0]:
                    rule_options.append({'name': rrow[0]})

        cursor.close()
        conn.close()

        total_pages = (total_count + page_size - 1) // page_size

        resp = {
            'success': True,
            'items': items,
            'total': total_count,
            'page': page,
            'page_size': page_size,
            'total_pages': total_pages,
            'status_counts': {
                'corrected': status_counts.get('corrected', 0),
                'normal': status_counts.get('normal', 0),
                'reverted': status_counts.get('reverted', 0),
            },
        }
        if rule_options:
            resp['rule_options'] = rule_options

        return JsonResponse(resp)
    except Exception as e:
        if conn:
            try:
                conn.close()
            except Exception:
                pass
        return safe_error(e)


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


def review_reasons(request):
    """정상 처리 이유 목록 조회 API (GET) — 코드 상수에서 반환"""
    from apps.common.constants import get_reasons
    check_type = request.GET.get('check_type', 'null_check')
    reasons = [{'text': r} for r in get_reasons(check_type)]
    return JsonResponse({'success': True, 'reasons': reasons})


# ============================================================
# 검수 확인 기록 API (Check Log) — Layer 1에서 이전
# ============================================================

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


def check_status(request):
    """날짜별 검수 확인 상태 조회"""
    date_str = request.GET.get('date')
    layer = int(request.GET.get('layer', 1))
    include_detail = request.GET.get('detail', '0') == '1'

    if not date_str:
        return JsonResponse({'success': False, 'error': '날짜를 지정하세요.'}, status=400)

    conn = get_dx_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT id, section, expected_count, actual_count, rate, status, memo,
                   created_id, created_at, updated_id, updated_at, confirm_step
            FROM monitoring_check_log
            WHERE crawl_date = %s AND layer = %s AND is_del = 0
            ORDER BY id
        """, (date_str, layer))

        rows = cursor.fetchall()
        sections = {}
        for row in rows:
            sections[row[1]] = {
                'id': row[0],
                'expected_count': row[2],
                'actual_count': row[3],
                'rate': float(row[4]) if row[4] else 0,
                'status': row[5],
                'memo': row[6] or '',
                'created_id': row[7],
                'created_at': row[8].isoformat() if row[8] else None,
                'updated_id': row[9],
                'updated_at': row[10].isoformat() if row[10] else None,
                'confirm_step': row[11],
            }

        check_log_ids = [sections[s]['id'] for s in sections]
        if include_detail and check_log_ids:
            placeholders = ','.join(['%s'] * len(check_log_ids))
            cursor.execute(f"""
                SELECT d.id, d.section, d.category, d.time_slot, d.retailer,
                       d.item_name, d.expected_count, d.actual_count, d.rate, d.status,
                       d.issue_id, d.confirm_step
                FROM monitoring_check_log_detail d
                WHERE d.check_log_id IN ({placeholders})
                ORDER BY d.confirm_step, d.id
            """, check_log_ids)
            for dr in cursor.fetchall():
                sec_key = dr[1]
                step = dr[11]
                if sec_key in sections:
                    cur_step = sections[sec_key]['confirm_step']
                    detail_key = 'details' if step == cur_step else 'details_step1'
                    if detail_key not in sections[sec_key]:
                        sections[sec_key][detail_key] = []
                    sections[sec_key][detail_key].append({
                        'detail_id': dr[0],
                        'category': dr[2], 'time_slot': dr[3],
                        'retailer': dr[4], 'item_name': dr[5],
                        'expected_count': dr[6], 'actual_count': dr[7],
                        'rate': float(dr[8]) if dr[8] else 0, 'status': dr[9],
                        'issue_id': dr[10],
                    })

        target_count = _get_target_sections(date_str)
        return JsonResponse({
            'success': True,
            'checked_all': len(sections) >= target_count,
            'checked_count': len(sections),
            'total_sections': target_count,
            'sections': sections
        })
    except Exception as e:
        return safe_error(e, 'db')
    finally:
        cursor.close()
        conn.close()


@require_POST
def check_save(request):
    """검수 확인 저장 (step=1: 1차 확인, step=2: 2차 완료)"""
    try:
        data = json.loads(request.body)
        date_str = data.get('date')
        layer = data.get('layer', 1)
        step = data.get('step', 1)
        sections = data.get('sections', [])
        username = request.user.username if request.user.is_authenticated else ''
        now = datetime.now()

        if not date_str or not sections:
            return JsonResponse({'success': False, 'error': '필수 파라미터가 누락되었습니다.'}, status=400)

        conn = get_dx_connection()
        cursor = conn.cursor()
        try:
            for s in sections:
                section = s.get('section', '')
                if section not in ALL_SECTIONS:
                    continue

                details = s.get('details', [])
                if details:
                    expected = sum(d.get('expected_count', 0) for d in details)
                    actual = sum(d.get('actual_count', 0) for d in details)
                else:
                    expected = s.get('expected_count', 0)
                    actual = s.get('actual_count', 0)
                rate = round(actual / expected * 100) if expected > 0 else s.get('rate', 0)

                if step == 2:
                    # 2차 완료: 미해결 이슈 체크
                    cursor.execute("""
                        SELECT COUNT(*) FROM monitoring_check_log_issues
                        WHERE crawl_date = %s AND section = %s AND is_del = 0
                          AND resolution_status = 'open'
                    """, (date_str, section))
                    open_count = cursor.fetchone()[0]
                    if open_count > 0:
                        conn.rollback()
                        return JsonResponse({
                            'success': False,
                            'error': '미해결 이슈 ' + str(open_count) + '건이 있습니다. 이슈를 먼저 처리하세요.'
                        }, status=400)

                    # check_log UPDATE (confirm_step=2, 최신 수치 반영)
                    cursor.execute("""
                        UPDATE monitoring_check_log
                        SET confirm_step = 2, expected_count = %s, actual_count = %s,
                            rate = %s, status = %s, updated_id = %s, updated_at = %s
                        WHERE crawl_date = %s AND layer = %s AND section = %s AND is_del = 0
                    """, (expected, actual, rate, s.get('status', 'OK'),
                          username, now, date_str, layer, section))

                    # 기존 check_log_id 조회
                    cursor.execute("""
                        SELECT id FROM monitoring_check_log
                        WHERE crawl_date = %s AND layer = %s AND section = %s AND is_del = 0
                    """, (date_str, layer, section))
                    row = cursor.fetchone()
                    if not row:
                        # 1차 없이 바로 2차 (100% 섹션)
                        cursor.execute("""
                            INSERT INTO monitoring_check_log
                                (crawl_date, layer, section, expected_count, actual_count,
                                 rate, status, memo, confirm_step, created_id, created_at)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 2, %s, %s)
                            RETURNING id
                        """, (
                            date_str, layer, section,
                            expected, actual, rate, s.get('status', 'OK'),
                            s.get('memo', ''), username, now
                        ))
                        row = cursor.fetchone()
                    check_log_id = row[0]

                    # detail 전체 INSERT (confirm_step=2)
                    for d in details:
                        cursor.execute("""
                            INSERT INTO monitoring_check_log_detail
                                (check_log_id, crawl_date, layer, section,
                                 category, time_slot, retailer, item_name,
                                 expected_count, actual_count, rate, status, confirm_step)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 2)
                        """, (
                            check_log_id, date_str, layer, section,
                            d.get('category', ''), d.get('time_slot', ''),
                            d.get('retailer', ''), d.get('item_name', ''),
                            d.get('expected_count', 0), d.get('actual_count', 0),
                            d.get('rate', 0), d.get('status', 'OK')
                        ))

                else:
                    # 1차 확인: 기존 soft-delete → INSERT 패턴
                    cursor.execute("""
                        UPDATE monitoring_check_log
                        SET is_del = 1, updated_id = %s, updated_at = %s
                        WHERE crawl_date = %s AND layer = %s AND section = %s AND is_del = 0
                    """, (username, now, date_str, layer, section))

                    cursor.execute("""
                        INSERT INTO monitoring_check_log
                            (crawl_date, layer, section, expected_count, actual_count,
                             rate, status, memo, confirm_step, created_id, created_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 1, %s, %s)
                        RETURNING id
                    """, (
                        date_str, layer, section,
                        expected, actual,
                        rate, s.get('status', 'OK'), s.get('memo', ''),
                        username, now
                    ))
                    check_log_id = cursor.fetchone()[0]

                    # detail: 이상치(status≠OK)만 INSERT (confirm_step=1)
                    for d in details:
                        if d.get('status', 'OK') != 'OK':
                            cursor.execute("""
                                INSERT INTO monitoring_check_log_detail
                                    (check_log_id, crawl_date, layer, section,
                                     category, time_slot, retailer, item_name,
                                     expected_count, actual_count, rate, status, confirm_step)
                                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 1)
                            """, (
                                check_log_id, date_str, layer, section,
                                d.get('category', ''), d.get('time_slot', ''),
                                d.get('retailer', ''), d.get('item_name', ''),
                                d.get('expected_count', 0), d.get('actual_count', 0),
                                d.get('rate', 0), d.get('status', 'OK')
                            ))

                    # 수요증감율 부족 키워드 저장
                    keywords = s.get('keywords', [])
                    if keywords:
                        for kw in keywords:
                            cursor.execute("""
                                INSERT INTO monitoring_check_log_keywords
                                    (check_log_id, crawl_date, category, event_name,
                                     product_name, event_date, created_id, created_at)
                                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                            """, (
                                check_log_id, date_str,
                                kw.get('category', ''), kw.get('event_name', ''),
                                kw.get('product_name', ''), kw.get('event_date'),
                                username, now
                            ))

            conn.commit()
            return JsonResponse({'success': True, 'saved_count': len(sections), 'step': step})
        finally:
            cursor.close()
            conn.close()
    except Exception as e:
        return safe_error(e, 'save')


@require_POST
def check_delete(request):
    """검수 확인 취소 (step에 따라 다른 동작)"""
    try:
        data = json.loads(request.body)
        date_str = data.get('date')
        section = data.get('section')
        layer = data.get('layer', 1)
        step = data.get('step', 0)
        delete_memo = data.get('delete_memo', '')
        username = request.user.username if request.user.is_authenticated else ''
        now = datetime.now()

        if not date_str:
            return JsonResponse({'success': False, 'error': '날짜를 지정하세요.'}, status=400)

        conn = get_dx_connection()
        cursor = conn.cursor()
        try:
            if step == 2 and section:
                # 2차 완료 취소
                cursor.execute("""
                    SELECT id, updated_at FROM monitoring_check_log
                    WHERE crawl_date = %s AND layer = %s AND section = %s AND is_del = 0
                """, (date_str, layer, section))
                row = cursor.fetchone()
                if row:
                    check_log_id = row[0]
                    # 1차→2차 UPDATE 시 updated_at이 설정됨, 바로 2차 INSERT 시 NULL
                    has_step1 = row[1] is not None
                    # step2 detail 삭제
                    cursor.execute("""
                        DELETE FROM monitoring_check_log_detail
                        WHERE check_log_id = %s AND confirm_step = 2
                    """, (check_log_id,))
                    if has_step1:
                        # 1차 기록 있음 → confirm_step=1로 되돌림
                        cursor.execute("""
                            UPDATE monitoring_check_log
                            SET confirm_step = 1, updated_id = %s, updated_at = %s, delete_memo = %s
                            WHERE id = %s
                        """, (username, now, delete_memo, check_log_id))
                    else:
                        # 1차 없이 바로 2차였음 → 레코드 삭제 (soft-delete) + keywords 삭제
                        cursor.execute("DELETE FROM monitoring_check_log_keywords WHERE check_log_id = %s", (check_log_id,))
                        cursor.execute("""
                            UPDATE monitoring_check_log
                            SET is_del = 1, updated_id = %s, updated_at = %s, delete_memo = %s
                            WHERE id = %s
                        """, (username, now, delete_memo, check_log_id))
            elif section:
                # 1차 확인 취소: 기존 soft-delete + keywords 삭제
                cursor.execute("""
                    SELECT id FROM monitoring_check_log
                    WHERE crawl_date = %s AND layer = %s AND section = %s AND is_del = 0
                """, (date_str, layer, section))
                del_row = cursor.fetchone()
                if del_row:
                    cursor.execute("DELETE FROM monitoring_check_log_keywords WHERE check_log_id = %s", (del_row[0],))
                cursor.execute("""
                    UPDATE monitoring_check_log
                    SET is_del = 1, updated_id = %s, updated_at = %s, delete_memo = %s
                    WHERE crawl_date = %s AND layer = %s AND section = %s AND is_del = 0
                """, (username, now, delete_memo, date_str, layer, section))
            else:
                cursor.execute("""
                    UPDATE monitoring_check_log
                    SET is_del = 1, updated_id = %s, updated_at = %s, delete_memo = %s
                    WHERE crawl_date = %s AND layer = %s AND is_del = 0
                """, (username, now, delete_memo, date_str, layer))

            conn.commit()
            return JsonResponse({'success': True, 'deleted': cursor.rowcount})
        finally:
            cursor.close()
            conn.close()
    except Exception as e:
        return safe_error(e, 'delete')


@require_POST
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


# ============================================================
# 수집 이슈 (Collection Issues)
# ============================================================

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


@require_POST
def corrections_cancel(request):
    """정상처리 일괄 취소 API"""
    try:
        data = json.loads(request.body)
        ids = data.get('ids', [])
        cancel_memo = data.get('cancel_memo', '')
        username = request.user.username if request.user.is_authenticated else ''
        now = datetime.now()

        if not ids or not isinstance(ids, list):
            return JsonResponse({'success': False, 'error': '취소할 항목을 선택하세요.'}, status=400)

        conn = get_dx_connection()
        cursor = conn.cursor()
        try:
            placeholders = ','.join(['%s'] * len(ids))
            cursor.execute(f"""
                UPDATE monitoring_corrections
                SET status = 'reverted', updated_id = %s, updated_at = %s, cancel_memo = %s
                WHERE id IN ({placeholders}) AND status = 'normal'
            """, [username, now, cancel_memo or None] + ids)
            cancelled = cursor.rowcount
            conn.commit()
            return JsonResponse({'success': True, 'cancelled': cancelled})
        finally:
            cursor.close()
            conn.close()
    except Exception as e:
        return safe_error(e, 'corrections_cancel')
