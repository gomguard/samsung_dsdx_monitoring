"""
Layer 1 API: 기본 통계 검수 (Foundational Integrity Check)
- 수집 직후 행의 개수가 예상 범위 내에 있는지 확인
- 필수 컬럼이 모두 존재하는지 확인
- 리테일러별 개별 검증
"""

from django.http import JsonResponse
from datetime import datetime, timedelta
from apps.common.db import get_dx_connection


# 리테일러 설정
RETAILERS = ['amazon', 'bestbuy', 'walmart']
EXPECTED_PER_RETAILER = 300  # 기대값
OK_THRESHOLD = 250           # 정상 기준 (이상이면 OK)
WARNING_THRESHOLD = 200      # 주의 기준 (이상이면 WARNING, 미만이면 CRITICAL)


def check_retailer_data(rows):
    """
    리테일러별 데이터 검증
    Returns: (retailer_details, total_count, all_ok)
    """
    retailer_counts = {r.lower(): 0 for r in RETAILERS}

    # 수집된 데이터 카운트
    for row in rows:
        retailer_name = row[0].lower() if row[0] else ''
        count = row[1]
        if retailer_name in retailer_counts:
            retailer_counts[retailer_name] = count

    retailer_details = []
    total_count = 0
    statuses = []

    for retailer in RETAILERS:
        count = retailer_counts[retailer]
        total_count += count

        # 상태 판정: 250 이상 = OK, 200~249 = WARNING, 200 미만 = CRITICAL
        if count >= OK_THRESHOLD:
            status = 'OK'
        elif count >= WARNING_THRESHOLD:
            status = 'WARNING'
        else:
            status = 'CRITICAL'

        statuses.append(status)
        retailer_details.append({
            'retailer': retailer.capitalize(),
            'count': count,
            'expected': EXPECTED_PER_RETAILER,
            'ok_threshold': OK_THRESHOLD,
            'warning_threshold': WARNING_THRESHOLD,
            'status': status
        })

    # 전체 상태 결정
    if 'CRITICAL' in statuses:
        overall_status = 'CRITICAL'
    elif 'WARNING' in statuses:
        overall_status = 'WARNING'
    else:
        overall_status = 'OK'

    return retailer_details, total_count, overall_status


def layer_stats(request):
    """Layer 1 통계 API - 일일 수집량 기본 검증 (제품군별 통합)"""

    # 날짜 파라미터 처리 (기본값: 전일자)
    date_str = request.GET.get('date')
    today = datetime.now().date()

    if date_str:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    else:
        target_date = today - timedelta(days=1)  # 기본값: 전일자

    # 다음날 (오후 시간대 종료 기준)
    next_day = target_date + timedelta(days=1)

    results = {
        'timestamp': datetime.now().isoformat(),
        'target_date': str(target_date),
        'today': str(today),
        'layer': 1,
        'name': '기본 통계 검수',
        'checks': [],
        'failed_items': [],
        'thresholds': {
            'expected': EXPECTED_PER_RETAILER,
            'ok': OK_THRESHOLD,
            'warning': WARNING_THRESHOLD,
            'description': f'정상: {OK_THRESHOLD}건 이상 | 주의: {WARNING_THRESHOLD}~{OK_THRESHOLD-1}건 | 위험: {WARNING_THRESHOLD}건 미만'
        },
        'summary': {
            'total_checked': 0,
            'passed': 0,
            'failed': 0,
            'pass_rate': 0,
            'status': 'OK'
        }
    }

    try:
        conn = get_dx_connection()
        cursor = conn.cursor()

        # ============================================================
        # 시간대 정의 (선택한 날짜 기준 오전/오후)
        # 한국 오전 9시 = UTC 00:00
        # 한국 오후 9시 = UTC 12:00
        # ============================================================

        # 현재 시간 기준 PENDING 여부 판단
        now = datetime.now()
        now_hour = now.hour

        # 오전 수집: target_date UTC 00:00 ~ 12:00 (KST 09:00 ~ 21:00)
        # 오후 수집: target_date UTC 12:00 ~ next_day UTC 00:00 (KST 21:00 ~ 다음날 09:00)

        # PENDING 판단: 조회 날짜가 오늘인 경우만 시간 체크
        am_pending = (target_date == today and now_hour < 9)
        pm_pending = (target_date == today and now_hour < 21)

        time_slots = [
            {
                'name': '오전',
                'start': f'{target_date} 00:00:00',
                'end': f'{target_date} 12:00:00',
                'utc_time': f'{target_date} 00:00',
                'kr_time': f'{target_date} 09:00',
                'is_pending': am_pending
            },
            {
                'name': '오후',
                'start': f'{target_date} 12:00:00',
                'end': f'{next_day} 00:00:00',
                'utc_time': f'{target_date} 12:00',
                'kr_time': f'{target_date} 21:00',
                'is_pending': pm_pending
            },
        ]

        # ============================================================
        # TV Retail 검증 (통합)
        # ============================================================
        tv_time_slots = []
        tv_total_count = 0
        tv_slot_statuses = []

        for slot in time_slots:
            cursor.execute("""
                SELECT account_name, COUNT(*) as cnt
                FROM tv_retail_com
                WHERE crawl_datetime::timestamp >= %s
                AND crawl_datetime::timestamp < %s
                GROUP BY account_name
            """, (slot['start'], slot['end']))

            rows = cursor.fetchall()

            if slot['is_pending']:
                total = sum(row[1] for row in rows) if rows else 0
                tv_time_slots.append({
                    'name': slot['name'],
                    'utc_time': slot['utc_time'],
                    'kr_time': slot['kr_time'],
                    'total': total,
                    'expected': EXPECTED_PER_RETAILER * len(RETAILERS),
                    'status': 'PENDING',
                    'retailers': []
                })
            else:
                retailer_details, total, slot_status = check_retailer_data(rows)
                tv_total_count += total
                tv_slot_statuses.append(slot_status)

                tv_time_slots.append({
                    'name': slot['name'],
                    'utc_time': slot['utc_time'],
                    'kr_time': slot['kr_time'],
                    'total': total,
                    'expected': EXPECTED_PER_RETAILER * len(RETAILERS),
                    'status': slot_status,
                    'retailers': retailer_details
                })

                # 실패 항목 추가
                for r in retailer_details:
                    if r['status'] != 'OK':
                        error_type = '수집 없음' if r['count'] == 0 else ('주의' if r['status'] == 'WARNING' else '수집량 부족')
                        results['failed_items'].append({
                            'source': f"TV Retail - {r['retailer']}",
                            'error_type': error_type,
                            'expected': f">= {OK_THRESHOLD}",
                            'actual': r['count'],
                            'timestamp': f"TV {slot['name']}"
                        })

        # TV 전체 상태 결정
        if 'CRITICAL' in tv_slot_statuses:
            tv_overall_status = 'CRITICAL'
        elif 'WARNING' in tv_slot_statuses:
            tv_overall_status = 'WARNING'
        elif not tv_slot_statuses:
            tv_overall_status = 'PENDING'
        else:
            tv_overall_status = 'OK'

        # 활성 슬롯 수 계산
        tv_active_slots = len([s for s in tv_time_slots if s['status'] != 'PENDING'])
        tv_ok_slots = len([s for s in tv_time_slots if s['status'] == 'OK'])

        results['checks'].append({
            'name': 'TV Retail',
            'description': f'{tv_ok_slots}/{tv_active_slots} 시간대 정상',
            'actual': tv_total_count,
            'expected_min': EXPECTED_PER_RETAILER * len(RETAILERS) * tv_active_slots,
            'status': tv_overall_status,
            'time_slots': tv_time_slots
        })

        # ============================================================
        # HHP Retail 검증 (통합)
        # ============================================================
        hhp_time_slots = []
        hhp_total_count = 0
        hhp_slot_statuses = []

        for slot in time_slots:
            cursor.execute("""
                SELECT account_name, COUNT(*) as cnt
                FROM hhp_retail_com
                WHERE crawl_strdatetime::timestamp >= %s
                AND crawl_strdatetime::timestamp < %s
                GROUP BY account_name
            """, (slot['start'], slot['end']))

            rows = cursor.fetchall()

            if slot['is_pending']:
                total = sum(row[1] for row in rows) if rows else 0
                hhp_time_slots.append({
                    'name': slot['name'],
                    'utc_time': slot['utc_time'],
                    'kr_time': slot['kr_time'],
                    'total': total,
                    'expected': EXPECTED_PER_RETAILER * len(RETAILERS),
                    'status': 'PENDING',
                    'retailers': []
                })
            else:
                retailer_details, total, slot_status = check_retailer_data(rows)
                hhp_total_count += total
                hhp_slot_statuses.append(slot_status)

                hhp_time_slots.append({
                    'name': slot['name'],
                    'utc_time': slot['utc_time'],
                    'kr_time': slot['kr_time'],
                    'total': total,
                    'expected': EXPECTED_PER_RETAILER * len(RETAILERS),
                    'status': slot_status,
                    'retailers': retailer_details
                })

                for r in retailer_details:
                    if r['status'] != 'OK':
                        error_type = '수집 없음' if r['count'] == 0 else ('주의' if r['status'] == 'WARNING' else '수집량 부족')
                        results['failed_items'].append({
                            'source': f"HHP Retail - {r['retailer']}",
                            'error_type': error_type,
                            'expected': f">= {OK_THRESHOLD}",
                            'actual': r['count'],
                            'timestamp': f"HHP {slot['name']}"
                        })

        # HHP 전체 상태 결정
        if 'CRITICAL' in hhp_slot_statuses:
            hhp_overall_status = 'CRITICAL'
        elif 'WARNING' in hhp_slot_statuses:
            hhp_overall_status = 'WARNING'
        elif not hhp_slot_statuses:
            hhp_overall_status = 'PENDING'
        else:
            hhp_overall_status = 'OK'

        hhp_active_slots = len([s for s in hhp_time_slots if s['status'] != 'PENDING'])
        hhp_ok_slots = len([s for s in hhp_time_slots if s['status'] == 'OK'])

        results['checks'].append({
            'name': 'HHP Retail',
            'description': f'{hhp_ok_slots}/{hhp_active_slots} 시간대 정상',
            'actual': hhp_total_count,
            'expected_min': EXPECTED_PER_RETAILER * len(RETAILERS) * hhp_active_slots,
            'status': hhp_overall_status,
            'time_slots': hhp_time_slots
        })

        # ============================================================
        # TV Sentiment 검증
        # ============================================================
        # Sentiment 분석은 다음날 UTC 01시(KST 10시)에 실행됨
        # 따라서 조회 날짜가 오늘이면 아직 분석 전(PENDING)
        sentiment_pending = (target_date >= today)

        # TV 분석 대상 (SKU가 유효한 항목만)
        cursor.execute("""
            SELECT COUNT(*)
            FROM tv_retail_com r
            INNER JOIN tv_item_mst m ON r.item = m.item AND r.account_name = m.account_name
            WHERE r.crawl_datetime::timestamp >= %s AND r.crawl_datetime::timestamp < %s
              AND m.sku IS NOT NULL
              AND m.sku != ''
              AND m.sku != 'no sku'
              AND m.sku != 'Not TV'
        """, (f'{target_date} 00:00:00', f'{next_day} 00:00:00'))
        tv_sentiment_target = cursor.fetchone()[0] or 0

        # TV 분석 완료
        cursor.execute("""
            SELECT COUNT(*)
            FROM tv_retail_sentiment s
            JOIN tv_retail_com r ON s.retail_com_id = r.id
            WHERE r.crawl_datetime::timestamp >= %s AND r.crawl_datetime::timestamp < %s
        """, (f'{target_date} 00:00:00', f'{next_day} 00:00:00'))
        tv_sentiment_analyzed = cursor.fetchone()[0] or 0

        # TV 리테일러별/시간대별 상세
        cursor.execute("""
            SELECT
                LOWER(r.account_name),
                CASE WHEN EXTRACT(HOUR FROM r.crawl_datetime::timestamp) < 1 THEN '오전' ELSE '오후' END as period,
                COUNT(*) as target_count
            FROM tv_retail_com r
            INNER JOIN tv_item_mst m ON r.item = m.item AND r.account_name = m.account_name
            WHERE r.crawl_datetime::timestamp >= %s AND r.crawl_datetime::timestamp < %s
              AND m.sku IS NOT NULL
              AND m.sku != ''
              AND m.sku != 'no sku'
              AND m.sku != 'Not TV'
            GROUP BY LOWER(r.account_name), period
            ORDER BY LOWER(r.account_name), period
        """, (f'{target_date} 00:00:00', f'{next_day} 00:00:00'))
        tv_sent_target_details = {f"{row[0]}_{row[1]}": row[2] for row in cursor.fetchall()}

        cursor.execute("""
            SELECT
                LOWER(r.account_name),
                CASE WHEN EXTRACT(HOUR FROM r.crawl_datetime::timestamp) < 1 THEN '오전' ELSE '오후' END as period,
                COUNT(*) as analyzed_count
            FROM tv_retail_sentiment s
            JOIN tv_retail_com r ON s.retail_com_id = r.id
            WHERE r.crawl_datetime::timestamp >= %s AND r.crawl_datetime::timestamp < %s
            GROUP BY LOWER(r.account_name), period
            ORDER BY LOWER(r.account_name), period
        """, (f'{target_date} 00:00:00', f'{next_day} 00:00:00'))
        tv_sent_analyzed_details = {f"{row[0]}_{row[1]}": row[2] for row in cursor.fetchall()}

        # TV Sentiment 시간대별 데이터 (Retail과 동일한 구조)
        tv_sentiment_time_slots = []
        tv_sentiment_ok_slots = 0
        tv_sentiment_active_slots = 0

        # Sentiment 시간대 정의
        # 분석 실행: 다음날 UTC 01시 (KST 10시)
        sentiment_time_slots_info = [
            {'period': '오전', 'utc_time': f'{next_day} 01:00', 'kr_time': f'{next_day} 10:00'},
            {'period': '오후', 'utc_time': f'{next_day} 01:00', 'kr_time': f'{next_day} 10:00'},
        ]

        for slot_info in sentiment_time_slots_info:
            period = slot_info['period']
            slot_target = 0
            slot_analyzed = 0
            retailers_data = []

            for retailer in RETAILERS:
                key = f"{retailer}_{period}"
                target = tv_sent_target_details.get(key, 0)
                analyzed = tv_sent_analyzed_details.get(key, 0)
                rate = round((analyzed / target * 100), 1) if target > 0 else 0

                if sentiment_pending:
                    status = 'PENDING'
                elif target == 0:
                    status = 'PENDING'
                elif rate >= 100:
                    status = 'OK'
                elif rate >= 90:
                    status = 'WARNING'
                else:
                    status = 'CRITICAL'

                retailers_data.append({
                    'name': retailer.capitalize(),
                    'target': target,
                    'analyzed': analyzed,
                    'rate': rate,
                    'status': status
                })

                slot_target += target
                slot_analyzed += analyzed

            slot_rate = round((slot_analyzed / slot_target * 100), 1) if slot_target > 0 else 0
            if sentiment_pending:
                slot_status = 'PENDING'
            elif slot_target == 0:
                slot_status = 'PENDING'
            elif slot_rate >= 100:
                slot_status = 'OK'
            elif slot_rate >= 90:
                slot_status = 'WARNING'
            else:
                slot_status = 'CRITICAL'

            if slot_target > 0 and not sentiment_pending:
                tv_sentiment_active_slots += 1
                if slot_status == 'OK':
                    tv_sentiment_ok_slots += 1

            tv_sentiment_time_slots.append({
                'time': period,
                'utc_time': slot_info['utc_time'],
                'kr_time': slot_info['kr_time'],
                'target': slot_target,
                'analyzed': slot_analyzed,
                'rate': slot_rate,
                'status': slot_status,
                'retailers': retailers_data
            })

        tv_sentiment_rate = round((tv_sentiment_analyzed / tv_sentiment_target * 100), 1) if tv_sentiment_target > 0 else 0
        if sentiment_pending:
            tv_sentiment_status = 'PENDING'
        elif tv_sentiment_target == 0:
            tv_sentiment_status = 'PENDING'
        elif tv_sentiment_rate >= 100:
            tv_sentiment_status = 'OK'
        elif tv_sentiment_rate >= 90:
            tv_sentiment_status = 'WARNING'
        else:
            tv_sentiment_status = 'CRITICAL'

        results['checks'].append({
            'name': 'TV Sentiment',
            'description': f'{tv_sentiment_ok_slots}/{tv_sentiment_active_slots} 시간대 정상',
            'actual': tv_sentiment_analyzed,
            'target': tv_sentiment_target,
            'rate': tv_sentiment_rate,
            'status': tv_sentiment_status,
            'check_type': 'sentiment',
            'time_slots': tv_sentiment_time_slots
        })

        # ============================================================
        # HHP Sentiment 검증
        # ============================================================
        cursor.execute("""
            SELECT COUNT(*)
            FROM hhp_retail_com r
            INNER JOIN hhp_item_mst m ON r.item = m.item AND r.account_name = m.account_name
            WHERE r.crawl_strdatetime::timestamp >= %s AND r.crawl_strdatetime::timestamp < %s
              AND m.sku IS NOT NULL
              AND m.sku != ''
        """, (f'{target_date} 00:00:00', f'{next_day} 00:00:00'))
        hhp_sentiment_target = cursor.fetchone()[0] or 0

        cursor.execute("""
            SELECT COUNT(*)
            FROM hhp_retail_sentiment s
            JOIN hhp_retail_com r ON s.retail_com_id = r.id
            WHERE r.crawl_strdatetime::timestamp >= %s AND r.crawl_strdatetime::timestamp < %s
        """, (f'{target_date} 00:00:00', f'{next_day} 00:00:00'))
        hhp_sentiment_analyzed = cursor.fetchone()[0] or 0

        cursor.execute("""
            SELECT
                LOWER(r.account_name),
                CASE WHEN EXTRACT(HOUR FROM r.crawl_strdatetime::timestamp) < 1 THEN '오전' ELSE '오후' END as period,
                COUNT(*) as target_count
            FROM hhp_retail_com r
            INNER JOIN hhp_item_mst m ON r.item = m.item AND r.account_name = m.account_name
            WHERE r.crawl_strdatetime::timestamp >= %s AND r.crawl_strdatetime::timestamp < %s
              AND m.sku IS NOT NULL
              AND m.sku != ''
            GROUP BY LOWER(r.account_name), period
            ORDER BY LOWER(r.account_name), period
        """, (f'{target_date} 00:00:00', f'{next_day} 00:00:00'))
        hhp_sent_target_details = {f"{row[0]}_{row[1]}": row[2] for row in cursor.fetchall()}

        cursor.execute("""
            SELECT
                LOWER(r.account_name),
                CASE WHEN EXTRACT(HOUR FROM r.crawl_strdatetime::timestamp) < 1 THEN '오전' ELSE '오후' END as period,
                COUNT(*) as analyzed_count
            FROM hhp_retail_sentiment s
            JOIN hhp_retail_com r ON s.retail_com_id = r.id
            WHERE r.crawl_strdatetime::timestamp >= %s AND r.crawl_strdatetime::timestamp < %s
            GROUP BY LOWER(r.account_name), period
            ORDER BY LOWER(r.account_name), period
        """, (f'{target_date} 00:00:00', f'{next_day} 00:00:00'))
        hhp_sent_analyzed_details = {f"{row[0]}_{row[1]}": row[2] for row in cursor.fetchall()}

        # HHP Sentiment 시간대별 데이터 (Retail과 동일한 구조)
        hhp_sentiment_time_slots = []
        hhp_sentiment_ok_slots = 0
        hhp_sentiment_active_slots = 0

        for slot_info in sentiment_time_slots_info:
            period = slot_info['period']
            slot_target = 0
            slot_analyzed = 0
            retailers_data = []

            for retailer in RETAILERS:
                key = f"{retailer}_{period}"
                target = hhp_sent_target_details.get(key, 0)
                analyzed = hhp_sent_analyzed_details.get(key, 0)
                rate = round((analyzed / target * 100), 1) if target > 0 else 0

                if sentiment_pending:
                    status = 'PENDING'
                elif target == 0:
                    status = 'PENDING'
                elif rate >= 100:
                    status = 'OK'
                elif rate >= 90:
                    status = 'WARNING'
                else:
                    status = 'CRITICAL'

                retailers_data.append({
                    'name': retailer.capitalize(),
                    'target': target,
                    'analyzed': analyzed,
                    'rate': rate,
                    'status': status
                })

                slot_target += target
                slot_analyzed += analyzed

            slot_rate = round((slot_analyzed / slot_target * 100), 1) if slot_target > 0 else 0
            if sentiment_pending:
                slot_status = 'PENDING'
            elif slot_target == 0:
                slot_status = 'PENDING'
            elif slot_rate >= 100:
                slot_status = 'OK'
            elif slot_rate >= 90:
                slot_status = 'WARNING'
            else:
                slot_status = 'CRITICAL'

            if slot_target > 0 and not sentiment_pending:
                hhp_sentiment_active_slots += 1
                if slot_status == 'OK':
                    hhp_sentiment_ok_slots += 1

            hhp_sentiment_time_slots.append({
                'time': period,
                'utc_time': slot_info['utc_time'],
                'kr_time': slot_info['kr_time'],
                'target': slot_target,
                'analyzed': slot_analyzed,
                'rate': slot_rate,
                'status': slot_status,
                'retailers': retailers_data
            })

        hhp_sentiment_rate = round((hhp_sentiment_analyzed / hhp_sentiment_target * 100), 1) if hhp_sentiment_target > 0 else 0
        if sentiment_pending:
            hhp_sentiment_status = 'PENDING'
        elif hhp_sentiment_target == 0:
            hhp_sentiment_status = 'PENDING'
        elif hhp_sentiment_rate >= 100:
            hhp_sentiment_status = 'OK'
        elif hhp_sentiment_rate >= 90:
            hhp_sentiment_status = 'WARNING'
        else:
            hhp_sentiment_status = 'CRITICAL'

        results['checks'].append({
            'name': 'HHP Sentiment',
            'description': f'{hhp_sentiment_ok_slots}/{hhp_sentiment_active_slots} 시간대 정상',
            'actual': hhp_sentiment_analyzed,
            'target': hhp_sentiment_target,
            'rate': hhp_sentiment_rate,
            'status': hhp_sentiment_status,
            'check_type': 'sentiment',
            'time_slots': hhp_sentiment_time_slots
        })

        # ============================================================
        # Consumer (YouTube) 검증
        # ============================================================
        # 기대값(7일 평균) 대비 수집률 기준 (Sentiment와 동일)
        # 기준: 100% 이상 = OK, 90~99% = WARNING, 90% 미만 = CRITICAL

        # 전일 YouTube 수집량 (카테고리별)
        cursor.execute("""
            SELECT
                COALESCE(k.category, 'Unknown') as category,
                COUNT(*) as log_count,
                SUM(CASE WHEN l.status = 'completed' THEN 1 ELSE 0 END) as success_count,
                COALESCE(SUM(l.videos_collected), 0) as video_count,
                COALESCE(SUM(l.comments_collected), 0) as comment_count
            FROM youtube_collection_logs l
            LEFT JOIN youtube_keywords k ON l.keyword_id = k.id
            WHERE DATE(l.started_at) = %s
            GROUP BY k.category
            ORDER BY k.category
        """, (target_date,))
        youtube_today = cursor.fetchall()

        # 7일 평균 (전일 제외) - 로그 건수 기준
        cursor.execute("""
            SELECT
                category,
                ROUND(AVG(daily_log_count), 1) as avg_log_count,
                ROUND(AVG(daily_comment_count), 1) as avg_comment_count
            FROM (
                SELECT
                    COALESCE(k.category, 'Unknown') as category,
                    DATE(l.started_at) as log_date,
                    COUNT(*) as daily_log_count,
                    COALESCE(SUM(l.comments_collected), 0) as daily_comment_count
                FROM youtube_collection_logs l
                LEFT JOIN youtube_keywords k ON l.keyword_id = k.id
                WHERE DATE(l.started_at) >= %s - INTERVAL '8 days'
                  AND DATE(l.started_at) < %s
                GROUP BY k.category, DATE(l.started_at)
            ) daily_stats
            GROUP BY category
        """, (target_date, target_date))
        youtube_avg_rows = cursor.fetchall()
        youtube_avg = {row[0]: {'avg_video': float(row[1] or 0), 'avg_comment': float(row[2] or 0)} for row in youtube_avg_rows}

        # YouTube 카테고리별 상세 데이터
        youtube_categories = []
        youtube_total_actual = 0
        youtube_total_expected = 0
        youtube_statuses = []

        for row in youtube_today:
            category = row[0]
            log_count = row[1] or 0
            success_count = row[2]
            video_count = row[3] or 0
            comment_count = row[4] or 0

            avg_data = youtube_avg.get(category, {'avg_video': 0, 'avg_comment': 0})
            expected = avg_data['avg_video']  # 7일 평균 = 기대값

            # 수집률 계산 (Sentiment와 동일: actual / expected * 100)
            if expected > 0:
                rate = (log_count / expected) * 100
            else:
                rate = 100 if log_count > 0 else 0

            # 상태 판정 (Sentiment와 동일 기준)
            if expected == 0:
                status = 'OK' if log_count > 0 else 'WARNING'
            elif rate >= 100:
                status = 'OK'
            elif rate >= 90:
                status = 'WARNING'
            else:
                status = 'CRITICAL'

            youtube_statuses.append(status)
            youtube_total_actual += log_count
            youtube_total_expected += expected

            youtube_categories.append({
                'name': category,
                'log_count': log_count,
                'video_count': video_count,
                'comment_count': comment_count,
                'expected': round(expected),  # 기대값 (7일 평균)
                'rate': round(rate, 1),
                'status': status
            })

        # YouTube 전체 상태
        if youtube_total_expected > 0:
            youtube_overall_rate = (youtube_total_actual / youtube_total_expected) * 100
        else:
            youtube_overall_rate = 100 if youtube_total_actual > 0 else 0

        if youtube_total_expected == 0:
            youtube_overall_status = 'OK' if youtube_total_actual > 0 else 'WARNING'
        elif youtube_overall_rate >= 100:
            youtube_overall_status = 'OK'
        elif youtube_overall_rate >= 90:
            youtube_overall_status = 'WARNING'
        else:
            youtube_overall_status = 'CRITICAL'

        youtube_ok_count = len([s for s in youtube_statuses if s == 'OK'])

        # TV, HHP 순서로 정렬
        category_order = {'TV': 0, 'HHP': 1}
        youtube_categories.sort(key=lambda x: category_order.get(x['name'], 99))

        results['checks'].append({
            'name': 'Consumer (YouTube)',
            'description': f'{youtube_ok_count}/{len(youtube_statuses)} 카테고리 정상',
            'actual': youtube_total_actual,
            'expected': round(youtube_total_expected),
            'rate': round(youtube_overall_rate, 1),
            'status': youtube_overall_status,
            'check_type': 'youtube',
            'categories': youtube_categories
        })

        # ============================================================
        # Market Trend 검증
        # ============================================================
        # 실행시간: 미국시간 오후 11시 (UTC 기준으로 계산)
        # 기준: ±30% 이내 = OK, ±30~50% = WARNING, ±50% 초과 = CRITICAL

        # 미국 동부시간 오후 11시 = UTC 04:00 (다음날)
        # 조회일 기준으로 다음날 UTC 04:00에 실행됨
        from datetime import time as dt_time
        market_run_time = datetime.combine(next_day, dt_time(4, 0))  # 다음날 UTC 04:00
        market_pending = (now < market_run_time)

        # Market Trend 기대건수 (market_mst에서 product_line + content_type별 키워드 수)
        cursor.execute("""
            SELECT
                product_line,
                content_type,
                COUNT(*) as expected_count
            FROM market_mst
            WHERE analysis_type = 'trend'
            GROUP BY product_line, content_type
            ORDER BY product_line, content_type
        """)
        market_expected = {f"{row[0]}_{row[1]}": row[2] for row in cursor.fetchall()}

        # Market Trend 수집건수 (전일 데이터)
        cursor.execute("""
            SELECT
                m.product_line,
                m.content_type,
                COUNT(*) as collected_count
            FROM market_trend t
            INNER JOIN market_mst m ON m.analysis_type = 'trend' AND t.keyword = m.keyword
            WHERE DATE(t.crawl_at_local_time) = %s
            GROUP BY m.product_line, m.content_type
        """, (target_date,))
        market_collected = {f"{row[0]}_{row[1]}": row[2] for row in cursor.fetchall()}

        # 7일 평균 수집건수
        cursor.execute("""
            SELECT
                product_line,
                content_type,
                ROUND(AVG(daily_count), 1) as avg_count
            FROM (
                SELECT
                    m.product_line,
                    m.content_type,
                    DATE(t.crawl_at_local_time) as log_date,
                    COUNT(*) as daily_count
                FROM market_trend t
                INNER JOIN market_mst m ON m.analysis_type = 'trend' AND t.keyword = m.keyword
                WHERE DATE(t.crawl_at_local_time) >= %s - INTERVAL '8 days'
                  AND DATE(t.crawl_at_local_time) < %s
                GROUP BY m.product_line, m.content_type, DATE(t.crawl_at_local_time)
            ) daily_stats
            GROUP BY product_line, content_type
        """, (target_date, target_date))
        market_avg = {f"{row[0]}_{row[1]}": float(row[2] or 0) for row in cursor.fetchall()}

        # Market Trend 카테고리별 상세 데이터
        market_categories = []
        market_total_collected = 0
        market_total_expected = 0
        market_statuses = []

        # TV, HHP 순서 정의
        product_order = {'TV': 0, 'HHP': 1}
        content_order = {'Event': 0, 'News': 1}

        for key, expected in market_expected.items():
            product_line, content_type = key.split('_')
            collected = market_collected.get(key, 0)
            avg = market_avg.get(key, 0)

            # 수집률 계산 (기대건수 대비)
            if expected > 0:
                rate = (collected / expected) * 100
            else:
                rate = 0 if collected == 0 else 100

            # 상태 판정: 100% = OK, 90%이상 = WARNING, 90%미만 = CRITICAL
            if market_pending:
                status = 'PENDING'
            elif expected == 0:
                status = 'PENDING'
            elif rate >= 100:
                status = 'OK'
            elif rate >= 90:
                status = 'WARNING'
            else:
                status = 'CRITICAL'

            market_statuses.append(status)
            market_total_collected += collected
            market_total_expected += expected

            market_categories.append({
                'product_line': product_line,
                'content_type': content_type,
                'collected': collected,
                'expected': expected,
                'avg': avg,
                'rate': round(rate, 1),
                'status': status
            })

        # TV, HHP 순서로 정렬 후 Event, News 순서로 정렬
        market_categories.sort(key=lambda x: (product_order.get(x['product_line'], 99), content_order.get(x['content_type'], 99)))

        # Market Trend 전체 상태
        if market_total_expected > 0:
            market_overall_rate = (market_total_collected / market_total_expected) * 100
        else:
            market_overall_rate = 0 if market_total_collected == 0 else 100

        if market_pending:
            market_overall_status = 'PENDING'
        elif market_total_expected == 0:
            market_overall_status = 'PENDING'
        elif market_overall_rate >= 100:
            market_overall_status = 'OK'
        elif market_overall_rate >= 90:
            market_overall_status = 'WARNING'
        else:
            market_overall_status = 'CRITICAL'

        market_ok_count = len([s for s in market_statuses if s == 'OK'])

        results['checks'].append({
            'name': 'Market Trend',
            'description': f'{market_ok_count}/{len(market_statuses)} 항목 정상',
            'actual': market_total_collected,
            'expected': market_total_expected,
            'rate': round(market_overall_rate, 1),
            'status': market_overall_status,
            'check_type': 'market_trend',
            'categories': market_categories,
            'run_time': {
                'utc': f'{next_day} 04:00',
                'us_eastern': f'{target_date} 23:00'
            }
        })

        # ============================================================
        # Market Competitor 검증 (경쟁품 분석)
        # ============================================================
        # 실행시간: 분기 첫날 (1/1, 4/1, 7/1, 10/1)
        # 카테고리별 (TV/HHP) 분석 건수 확인

        # 조회 날짜가 속한 분기 계산
        target_month = target_date.month
        target_year = target_date.year
        if target_month <= 3:
            quarter_start = f"{target_year}-01-01"
            quarter_end = f"{target_year}-03-31"
            quarter_name = "Q1"
        elif target_month <= 6:
            quarter_start = f"{target_year}-04-01"
            quarter_end = f"{target_year}-06-30"
            quarter_name = "Q2"
        elif target_month <= 9:
            quarter_start = f"{target_year}-07-01"
            quarter_end = f"{target_year}-09-30"
            quarter_name = "Q3"
        else:
            quarter_start = f"{target_year}-10-01"
            quarter_end = f"{target_year}-12-31"
            quarter_name = "Q4"

        # 분기 첫날인지 확인 (조회 날짜 기준)
        is_quarter_first = (target_date.day == 1 and target_date.month in [1, 4, 7, 10])

        # 해당 분기에 실행된 배치 조회 (분기 시작일 ~ 분기 종료일)
        cursor.execute("""
            SELECT batch_id, MAX(created_at) as last_run
            FROM market_comp_product
            WHERE batch_id IS NOT NULL
              AND created_at >= %s AND created_at < %s::date + INTERVAL '1 day'
            GROUP BY batch_id
            ORDER BY last_run DESC
            LIMIT 1
        """, (quarter_start, quarter_end))
        comp_batch_row = cursor.fetchone()
        comp_batch_id = comp_batch_row[0] if comp_batch_row else None
        comp_last_run = comp_batch_row[1] if comp_batch_row else None

        # 카테고리별 경쟁품 분석 건수 (해당 분기 배치)
        if comp_batch_id:
            cursor.execute("""
                SELECT
                    COALESCE(category, 'Unknown') as category,
                    COUNT(*) as collected_count
                FROM market_comp_product
                WHERE batch_id = %s
                GROUP BY category
                ORDER BY category
            """, (comp_batch_id,))
            comp_collected = {row[0]: row[1] for row in cursor.fetchall()}
        else:
            comp_collected = {}

        # 카테고리별 기대건수 (market_mst에서 samsung × comp 조합)
        cursor.execute("""
            SELECT
                product_line,
                COUNT(*) as samsung_count
            FROM market_mst
            WHERE analysis_type = 'competitor' AND content_type = 'samsung' AND is_active = true
            GROUP BY product_line
        """)
        samsung_counts = {row[0]: row[1] for row in cursor.fetchall()}

        cursor.execute("""
            SELECT
                product_line,
                COUNT(*) as comp_count
            FROM market_mst
            WHERE analysis_type = 'competitor' AND content_type = 'comp' AND is_active = true
            GROUP BY product_line
        """)
        comp_brand_counts = {row[0]: row[1] for row in cursor.fetchall()}

        # 기대건수 계산 (samsung_count × comp_count per category)
        comp_expected = {}
        for pl in ['TV', 'HHP']:
            samsung_cnt = samsung_counts.get(pl, 0)
            comp_cnt = comp_brand_counts.get(pl, 0)
            comp_expected[pl] = samsung_cnt * comp_cnt

        # Market Competitor 카테고리별 상세 데이터
        comp_categories = []
        comp_total_collected = 0
        comp_total_expected = 0
        comp_statuses = []

        for category in ['TV', 'HHP']:
            collected = comp_collected.get(category, 0)
            expected = comp_expected.get(category, 0)

            # 수집률 계산
            if expected > 0:
                rate = (collected / expected) * 100
            else:
                rate = 0 if collected == 0 else 100

            # 상태 판정
            if expected == 0:
                status = 'PENDING'
            elif rate >= 100:
                status = 'OK'
            elif rate >= 90:
                status = 'WARNING'
            else:
                status = 'CRITICAL'

            comp_statuses.append(status)
            comp_total_collected += collected
            comp_total_expected += expected

            comp_categories.append({
                'category': category,
                'collected': collected,
                'expected': expected,
                'rate': round(rate, 1),
                'status': status
            })

        # Market Competitor 전체 상태
        if comp_total_expected > 0:
            comp_overall_rate = (comp_total_collected / comp_total_expected) * 100
        else:
            comp_overall_rate = 0 if comp_total_collected == 0 else 100

        if comp_total_expected == 0:
            comp_overall_status = 'PENDING'
        elif comp_overall_rate >= 100:
            comp_overall_status = 'OK'
        elif comp_overall_rate >= 90:
            comp_overall_status = 'WARNING'
        else:
            comp_overall_status = 'CRITICAL'

        comp_ok_count = len([s for s in comp_statuses if s == 'OK'])

        results['checks'].append({
            'name': 'Market Competitor',
            'description': f'{comp_ok_count}/{len(comp_statuses)} 카테고리 정상',
            'actual': comp_total_collected,
            'expected': comp_total_expected,
            'rate': round(comp_overall_rate, 1),
            'status': comp_overall_status,
            'check_type': 'market_competitor',
            'categories': comp_categories,
            'batch_id': comp_batch_id,
            'last_run': comp_last_run.isoformat() if comp_last_run else None,
            'quarter': {
                'name': quarter_name,
                'start': quarter_start,
                'end': quarter_end
            },
            'is_target_date': is_quarter_first
        })

        # ============================================================
        # Market Competitor Event 검증 (경쟁품 이벤트 분석)
        # ============================================================
        # 실행시간: 매월 첫번째 월요일
        # 카테고리별 (TV/HHP) 이벤트 분석 건수 확인

        # 조회 날짜가 속한 월의 첫번째 월요일 계산
        first_day_of_month = target_date.replace(day=1)
        # 첫번째 월요일 찾기 (월요일 = 0)
        days_until_monday = (7 - first_day_of_month.weekday()) % 7
        if first_day_of_month.weekday() == 0:  # 1일이 월요일이면 그날이 첫번째 월요일
            first_monday = first_day_of_month
        else:
            first_monday = first_day_of_month + timedelta(days=days_until_monday)

        # 조회 날짜가 첫번째 월요일인지 확인
        is_first_monday = (target_date == first_monday)

        # 해당 월의 시작일과 종료일
        month_start = first_day_of_month.strftime('%Y-%m-%d')
        if target_date.month == 12:
            month_end_date = target_date.replace(year=target_date.year + 1, month=1, day=1) - timedelta(days=1)
        else:
            month_end_date = target_date.replace(month=target_date.month + 1, day=1) - timedelta(days=1)
        month_end = month_end_date.strftime('%Y-%m-%d')
        month_name = target_date.strftime('%Y년 %m월')

        # 해당 월에 실행된 이벤트 배치 조회 (월 시작일 ~ 월 종료일)
        cursor.execute("""
            SELECT batch_id, MAX(created_at) as last_run
            FROM market_comp_event
            WHERE batch_id IS NOT NULL
              AND created_at >= %s AND created_at < %s::date + INTERVAL '1 day'
            GROUP BY batch_id
            ORDER BY last_run DESC
            LIMIT 1
        """, (month_start, month_end))
        event_batch_row = cursor.fetchone()
        event_batch_id = event_batch_row[0] if event_batch_row else None
        event_last_run = event_batch_row[1] if event_batch_row else None

        # 카테고리별 이벤트 분석 건수 (해당 월 배치)
        if event_batch_id:
            cursor.execute("""
                SELECT
                    category,
                    COUNT(*) as collected_count
                FROM market_comp_event
                WHERE batch_id = %s
                GROUP BY category
                ORDER BY category
            """, (event_batch_id,))
            event_collected = {row[0]: row[1] for row in cursor.fetchall()}
        else:
            event_collected = {}

        # 기대건수: market_comp_product에서 comp_brand + comp_series_name 중복 제거 건수
        # (이벤트 분석은 경쟁사 브랜드 + 경쟁사 제품 조합별로 1회씩 진행)
        # comp_series_name이 'info_not_available'인 경우 제외
        event_expected = {}
        if comp_batch_id:
            cursor.execute("""
                SELECT
                    category,
                    COUNT(DISTINCT comp_brand || '||' || comp_series_name) as expected_count
                FROM market_comp_product
                WHERE batch_id = %s
                  AND comp_series_name != 'info_not_available'
                GROUP BY category
                ORDER BY category
            """, (comp_batch_id,))
            event_expected = {row[0]: row[1] for row in cursor.fetchall()}

        # Market Competitor Event 카테고리별 상세 데이터
        event_categories = []
        event_total_collected = 0
        event_total_expected = 0
        event_statuses = []

        for category in ['TV', 'HHP']:
            collected = event_collected.get(category, 0)
            expected = event_expected.get(category, 0)

            # 수집률 계산
            if expected > 0:
                rate = (collected / expected) * 100
            else:
                rate = 0 if collected == 0 else 100

            # 상태 판정
            if expected == 0:
                status = 'PENDING'
            elif rate >= 100:
                status = 'OK'
            elif rate >= 90:
                status = 'WARNING'
            else:
                status = 'CRITICAL'

            event_statuses.append(status)
            event_total_collected += collected
            event_total_expected += expected

            event_categories.append({
                'category': category,
                'collected': collected,
                'expected': expected,
                'rate': round(rate, 1),
                'status': status
            })

        # Market Competitor Event 전체 상태
        if event_total_expected > 0:
            event_overall_rate = (event_total_collected / event_total_expected) * 100
        else:
            event_overall_rate = 0 if event_total_collected == 0 else 100

        if event_total_expected == 0:
            event_overall_status = 'PENDING'
        elif event_overall_rate >= 100:
            event_overall_status = 'OK'
        elif event_overall_rate >= 90:
            event_overall_status = 'WARNING'
        else:
            event_overall_status = 'CRITICAL'

        event_ok_count = len([s for s in event_statuses if s == 'OK'])

        results['checks'].append({
            'name': 'Market Competitor Event',
            'description': f'{event_ok_count}/{len(event_statuses)} 카테고리 정상',
            'actual': event_total_collected,
            'expected': event_total_expected,
            'rate': round(event_overall_rate, 1),
            'status': event_overall_status,
            'check_type': 'market_competitor_event',
            'categories': event_categories,
            'batch_id': event_batch_id,
            'last_run': event_last_run.isoformat() if event_last_run else None,
            'month': {
                'name': month_name,
                'start': month_start,
                'end': month_end,
                'first_monday': first_monday.strftime('%Y-%m-%d')
            },
            'is_target_date': is_first_monday
        })

        # ============================================================
        # Market 수요증감율 검증 (openai_forecast_results)
        # ============================================================
        # 전일/오늘 현황 비교
        # 대상 키워드 수: 9주 이내 이벤트 키워드 - 1주 이내 제외 키워드
        # 수집 결과 수: openai_forecast_results 테이블

        def get_demand_stats(query_date):
            """수요증감율 통계 조회 (특정 날짜 기준)"""
            nine_weeks_later = query_date + timedelta(weeks=9)
            one_week_later = query_date + timedelta(weeks=1)

            # 9주 이내 키워드 수 (카테고리별)
            cursor.execute("""
                SELECT k.category, COUNT(*) as cnt
                FROM openai_keywords k
                JOIN openai_event_mst e ON k.event_name = e.event_name
                WHERE e.is_active = true
                AND e.event_date >= %s AND e.event_date <= %s
                GROUP BY k.category
            """, (query_date.strftime('%Y-%m-%d'), nine_weeks_later.strftime('%Y-%m-%d')))
            target_by_category = {row[0]: row[1] for row in cursor.fetchall()}

            # 1주 이내 키워드 수 (제외 대상, 카테고리별)
            cursor.execute("""
                SELECT k.category, COUNT(*) as cnt
                FROM openai_keywords k
                JOIN openai_event_mst e ON k.event_name = e.event_name
                WHERE e.is_active = true
                AND e.event_date >= %s AND e.event_date <= %s
                GROUP BY k.category
            """, (query_date.strftime('%Y-%m-%d'), one_week_later.strftime('%Y-%m-%d')))
            excluded_by_category = {row[0]: row[1] for row in cursor.fetchall()}

            # 수집 결과 수 (카테고리별)
            cursor.execute("""
                SELECT k.category, COUNT(*) as cnt
                FROM openai_forecast_results f
                JOIN openai_keywords k ON f.product_name = k.product_name
                    AND REPLACE(UPPER(f.event), '_', ' ') = UPPER(k.event_name)
                WHERE f.crawled_at::date = %s
                GROUP BY k.category
            """, (query_date.strftime('%Y-%m-%d'),))
            result_by_category = {row[0]: row[1] for row in cursor.fetchall()}

            return target_by_category, excluded_by_category, result_by_category

        # 조회일 통계
        target_demand, excluded_demand, result_demand = get_demand_stats(target_date)

        # 상태 판정 함수 (대상 키워드 대비 수집 결과 비율)
        def calc_demand_status(result_cnt, target_cnt):
            if target_cnt == 0:
                return 0, 'OK' if result_cnt == 0 else 'WARNING'
            ratio = result_cnt / target_cnt
            if ratio >= 0.9:  # 90% 이상
                return round(ratio * 100, 1), 'OK'
            elif ratio >= 0.7:  # 70~90%
                return round(ratio * 100, 1), 'WARNING'
            else:  # 70% 미만
                return round(ratio * 100, 1), 'CRITICAL'

        # 조회일 결과 (카테고리별)
        demand_categories = []
        for category in sorted(target_demand.keys()):
            target = target_demand.get(category, 0) - excluded_demand.get(category, 0)
            target = max(0, target)  # 음수 방지
            result_cnt = result_demand.get(category, 0)
            completion_pct, status = calc_demand_status(result_cnt, target)
            demand_categories.append({
                'category': category,
                'target': target,
                'collected': result_cnt,
                'rate': completion_pct,
                'status': status
            })

        # 전체 상태
        demand_total_target = sum(c['target'] for c in demand_categories)
        demand_total_collected = sum(c['collected'] for c in demand_categories)
        demand_rate, demand_status = calc_demand_status(demand_total_collected, demand_total_target)
        demand_ok_count = len([c for c in demand_categories if c['status'] == 'OK'])

        # 전체 상태 판정
        demand_all_statuses = [c['status'] for c in demand_categories]
        if any(s == 'CRITICAL' for s in demand_all_statuses):
            demand_overall_status = 'CRITICAL'
        elif any(s == 'WARNING' for s in demand_all_statuses):
            demand_overall_status = 'WARNING'
        else:
            demand_overall_status = 'OK'

        results['checks'].append({
            'name': 'Market 수요증감율',
            'description': f'{demand_ok_count}/{len(demand_categories)} 카테고리 정상',
            'status': demand_overall_status,
            'check_type': 'market_demand',
            'date': target_date.strftime('%Y-%m-%d'),
            'categories': demand_categories,
            'total_target': demand_total_target,
            'total_collected': demand_total_collected,
            'rate': demand_rate
        })

        # ============================================================
        # Market Promotion 검증 (거래선 프로모션)
        # ============================================================
        # 실행시간: 매주 월요일
        # 대상: 9주 이내 이벤트 × 7개 리테일러
        # 기준: 100% = OK, 90%+ = WARNING, 90%- = CRITICAL

        # 조회 날짜가 월요일인지 확인 (0=월요일)
        is_monday = target_date.weekday() == 0

        # 9주 이내 이벤트 수 조회
        promo_nine_weeks = target_date + timedelta(weeks=9)
        cursor.execute("""
            SELECT COUNT(DISTINCT id)
            FROM openai_event_mst
            WHERE is_active = true
              AND event_date IS NOT NULL
              AND event_date > %s
              AND event_date <= %s
        """, (target_date.strftime('%Y-%m-%d'), promo_nine_weeks.strftime('%Y-%m-%d')))
        promo_event_count = cursor.fetchone()[0] or 0

        # 해당 날짜에 수집된 프로모션 데이터 조회
        cursor.execute("""
            SELECT
                p.retailer,
                COUNT(*) as cnt
            FROM openai_retailer_promotions p
            WHERE p.crawled_at = %s
            GROUP BY p.retailer
            ORDER BY p.retailer
        """, (target_date.strftime('%Y-%m-%d'),))
        promo_retailer_counts = {row[0]: row[1] for row in cursor.fetchall()}

        # 총 수집건수
        promo_total_collected = sum(promo_retailer_counts.values())

        # 예상 수집건수: 대상 이벤트 수 × 7개 리테일러
        PROMO_RETAILERS = ['Amazon', 'Best Buy', 'Walmart', "Sam's Club", 'Home Depot', "Lowe's", 'Costco']
        promo_expected = promo_event_count * len(PROMO_RETAILERS)

        # 리테일러별 상세 데이터
        promo_retailers = []
        promo_ok_count = 0
        for retailer in PROMO_RETAILERS:
            collected = promo_retailer_counts.get(retailer, 0)
            expected = promo_event_count  # 각 리테일러별 이벤트 수만큼 기대

            if expected > 0:
                rate = (collected / expected) * 100
            else:
                rate = 0 if collected == 0 else 100

            # 상태 판정
            if not is_monday:
                status = 'PENDING'
            elif expected == 0:
                status = 'PENDING'
            elif rate >= 100:
                status = 'OK'
                promo_ok_count += 1
            elif rate >= 90:
                status = 'WARNING'
            else:
                status = 'CRITICAL'

            promo_retailers.append({
                'retailer': retailer,
                'collected': collected,
                'expected': expected,
                'rate': round(rate, 1),
                'status': status
            })

        # 전체 상태
        if promo_expected > 0:
            promo_overall_rate = (promo_total_collected / promo_expected) * 100
        else:
            promo_overall_rate = 0 if promo_total_collected == 0 else 100

        if not is_monday:
            promo_overall_status = 'PENDING'
        elif promo_expected == 0:
            promo_overall_status = 'PENDING'
        elif promo_overall_rate >= 100:
            promo_overall_status = 'OK'
        elif promo_overall_rate >= 90:
            promo_overall_status = 'WARNING'
        else:
            promo_overall_status = 'CRITICAL'

        results['checks'].append({
            'name': 'Market Promotion',
            'description': f'{promo_ok_count}/{len(PROMO_RETAILERS)} 리테일러 정상' if is_monday else '분석대상일 아님',
            'actual': promo_total_collected,
            'expected': promo_expected,
            'rate': round(promo_overall_rate, 1),
            'status': promo_overall_status,
            'check_type': 'market_promotion',
            'retailers': promo_retailers,
            'event_count': promo_event_count,
            'is_target_date': is_monday
        })

        cursor.close()
        conn.close()

        # Summary 계산
        all_statuses = [tv_overall_status, hhp_overall_status, tv_sentiment_status, hhp_sentiment_status, youtube_overall_status, market_overall_status, comp_overall_status, event_overall_status, demand_overall_status, promo_overall_status]
        active_statuses = [s for s in all_statuses if s != 'PENDING']

        passed = len([s for s in active_statuses if s == 'OK'])
        warning = len([s for s in active_statuses if s == 'WARNING'])
        failed = len([s for s in active_statuses if s == 'CRITICAL'])

        if failed > 0:
            overall_status = 'CRITICAL'
        elif warning > 0:
            overall_status = 'WARNING'
        else:
            overall_status = 'OK'

        results['summary'] = {
            'total_checked': len(active_statuses),
            'passed': passed,
            'warning': warning,
            'failed': failed,
            'pass_rate': round((passed / len(active_statuses) * 100), 1) if active_statuses else 0,
            'status': overall_status
        }

    except Exception as e:
        results['error'] = str(e)
        results['summary']['status'] = 'ERROR'

    return JsonResponse(results)


def retail_detail(request):
    """리테일 상세 현황 API"""
    date_str = request.GET.get('date')
    product_line = request.GET.get('type', 'tv')  # tv or hhp

    if date_str:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    else:
        target_date = (datetime.now() - timedelta(days=1)).date()

    try:
        conn = get_dx_connection()
        cursor = conn.cursor()

        if product_line == 'tv':
            cursor.execute("""
                SELECT
                    account_name as retailer,
                    COUNT(*) as total,
                    COUNT(CASE WHEN main_rank IS NOT NULL THEN 1 END) as main_count,
                    COUNT(CASE WHEN bsr_rank IS NOT NULL THEN 1 END) as bsr_count,
                    COUNT(CASE WHEN final_sku_price IS NOT NULL THEN 1 END) as price_count
                FROM tv_retail_com
                WHERE DATE(crawl_datetime::timestamp) = %s
                GROUP BY account_name
                ORDER BY account_name
            """, (target_date,))
        else:
            cursor.execute("""
                SELECT
                    account_name as retailer,
                    COUNT(*) as total,
                    COUNT(CASE WHEN main_rank IS NOT NULL THEN 1 END) as main_count,
                    COUNT(CASE WHEN bsr_rank IS NOT NULL THEN 1 END) as bsr_count,
                    COUNT(CASE WHEN final_sku_price IS NOT NULL THEN 1 END) as price_count
                FROM hhp_retail_com
                WHERE DATE(crawl_strdatetime::timestamp) = %s
                GROUP BY account_name
                ORDER BY account_name
            """, (target_date,))

        rows = cursor.fetchall()

        results = []
        for row in rows:
            results.append({
                'retailer': row[0],
                'total': row[1],
                'main_count': row[2],
                'bsr_count': row[3],
                'price_count': row[4],
                'completeness': round((row[4] / row[1] * 100), 1) if row[1] > 0 else 0
            })

        cursor.close()
        conn.close()

        return JsonResponse({
            'date': str(target_date),
            'product_line': product_line.upper(),
            'results': results,
            'total_retailers': len(results),
            'total_products': sum(r['total'] for r in results)
        })

    except Exception as e:
        return JsonResponse({'error': str(e)})


def sentiment_stats(request):
    """감성 분석 통계 API - 분석 대상 vs 저장된 결과"""
    date_str = request.GET.get('date')
    today = datetime.now().date()

    if date_str:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    else:
        target_date = today - timedelta(days=1)

    next_day = target_date + timedelta(days=1)

    # 시간대 범위
    start_time = f'{target_date} 00:00:00'
    end_time = f'{next_day} 00:00:00'

    results = {
        'timestamp': datetime.now().isoformat(),
        'target_date': str(target_date),
        'tv': {
            'target': 0,
            'analyzed': 0,
            'rate': 0,
            'status': 'PENDING',
            'details': []
        },
        'hhp': {
            'target': 0,
            'analyzed': 0,
            'rate': 0,
            'status': 'PENDING',
            'details': []
        }
    }

    try:
        conn = get_dx_connection()
        cursor = conn.cursor()

        # ============================================================
        # TV Sentiment 통계
        # ============================================================

        # TV 분석 대상 (SKU가 유효한 항목만)
        cursor.execute("""
            SELECT COUNT(*)
            FROM tv_retail_com r
            INNER JOIN tv_item_mst m ON r.item = m.item AND r.account_name = m.account_name
            WHERE r.crawl_datetime::timestamp >= %s AND r.crawl_datetime::timestamp < %s
              AND m.sku IS NOT NULL
              AND m.sku != ''
              AND m.sku != 'no sku'
              AND m.sku != 'Not TV'
        """, (start_time, end_time))
        tv_target = cursor.fetchone()[0] or 0

        # TV 분석 완료
        cursor.execute("""
            SELECT COUNT(*)
            FROM tv_retail_sentiment s
            JOIN tv_retail_com r ON s.retail_com_id = r.id
            WHERE r.crawl_datetime::timestamp >= %s AND r.crawl_datetime::timestamp < %s
        """, (start_time, end_time))
        tv_analyzed = cursor.fetchone()[0] or 0

        # TV 리테일러별/시간대별 상세
        cursor.execute("""
            SELECT
                r.account_name,
                CASE WHEN EXTRACT(HOUR FROM r.crawl_datetime::timestamp) < 1 THEN '오전' ELSE '오후' END as period,
                COUNT(*) as target_count
            FROM tv_retail_com r
            INNER JOIN tv_item_mst m ON r.item = m.item AND r.account_name = m.account_name
            WHERE r.crawl_datetime::timestamp >= %s AND r.crawl_datetime::timestamp < %s
              AND m.sku IS NOT NULL
              AND m.sku != ''
              AND m.sku != 'no sku'
              AND m.sku != 'Not TV'
            GROUP BY r.account_name, period
            ORDER BY r.account_name, period
        """, (start_time, end_time))
        tv_target_details = {f"{row[0]}_{row[1]}": row[2] for row in cursor.fetchall()}

        cursor.execute("""
            SELECT
                r.account_name,
                CASE WHEN EXTRACT(HOUR FROM r.crawl_datetime::timestamp) < 1 THEN '오전' ELSE '오후' END as period,
                COUNT(*) as analyzed_count
            FROM tv_retail_sentiment s
            JOIN tv_retail_com r ON s.retail_com_id = r.id
            WHERE r.crawl_datetime::timestamp >= %s AND r.crawl_datetime::timestamp < %s
            GROUP BY r.account_name, period
            ORDER BY r.account_name, period
        """, (start_time, end_time))
        tv_analyzed_details = {f"{row[0]}_{row[1]}": row[2] for row in cursor.fetchall()}

        # TV 상세 데이터 조합
        tv_details = []
        for retailer in RETAILERS:
            for period in ['오전', '오후']:
                key = f"{retailer}_{period}"
                target = tv_target_details.get(key, 0)
                analyzed = tv_analyzed_details.get(key, 0)
                rate = round((analyzed / target * 100), 1) if target > 0 else 0

                if target == 0:
                    status = 'PENDING'
                elif rate >= 100:
                    status = 'OK'
                elif rate >= 90:
                    status = 'WARNING'
                else:
                    status = 'CRITICAL'

                tv_details.append({
                    'retailer': retailer.capitalize(),
                    'period': period,
                    'target': target,
                    'analyzed': analyzed,
                    'rate': rate,
                    'status': status
                })

        tv_rate = round((tv_analyzed / tv_target * 100), 1) if tv_target > 0 else 0
        if tv_target == 0:
            tv_status = 'PENDING'
        elif tv_rate >= 100:
            tv_status = 'OK'
        elif tv_rate >= 90:
            tv_status = 'WARNING'
        else:
            tv_status = 'CRITICAL'

        results['tv'] = {
            'target': tv_target,
            'analyzed': tv_analyzed,
            'rate': tv_rate,
            'status': tv_status,
            'details': tv_details
        }

        # ============================================================
        # HHP Sentiment 통계
        # ============================================================

        # HHP 분석 대상
        cursor.execute("""
            SELECT COUNT(*)
            FROM hhp_retail_com r
            INNER JOIN hhp_item_mst m ON r.item = m.item AND r.account_name = m.account_name
            WHERE r.crawl_strdatetime::timestamp >= %s AND r.crawl_strdatetime::timestamp < %s
              AND m.sku IS NOT NULL
              AND m.sku != ''
        """, (start_time, end_time))
        hhp_target = cursor.fetchone()[0] or 0

        # HHP 분석 완료
        cursor.execute("""
            SELECT COUNT(*)
            FROM hhp_retail_sentiment s
            JOIN hhp_retail_com r ON s.retail_com_id = r.id
            WHERE r.crawl_strdatetime::timestamp >= %s AND r.crawl_strdatetime::timestamp < %s
        """, (start_time, end_time))
        hhp_analyzed = cursor.fetchone()[0] or 0

        # HHP 리테일러별/시간대별 상세
        cursor.execute("""
            SELECT
                r.account_name,
                CASE WHEN EXTRACT(HOUR FROM r.crawl_strdatetime::timestamp) < 1 THEN '오전' ELSE '오후' END as period,
                COUNT(*) as target_count
            FROM hhp_retail_com r
            INNER JOIN hhp_item_mst m ON r.item = m.item AND r.account_name = m.account_name
            WHERE r.crawl_strdatetime::timestamp >= %s AND r.crawl_strdatetime::timestamp < %s
              AND m.sku IS NOT NULL
              AND m.sku != ''
            GROUP BY r.account_name, period
            ORDER BY r.account_name, period
        """, (start_time, end_time))
        hhp_target_details = {f"{row[0]}_{row[1]}": row[2] for row in cursor.fetchall()}

        cursor.execute("""
            SELECT
                r.account_name,
                CASE WHEN EXTRACT(HOUR FROM r.crawl_strdatetime::timestamp) < 1 THEN '오전' ELSE '오후' END as period,
                COUNT(*) as analyzed_count
            FROM hhp_retail_sentiment s
            JOIN hhp_retail_com r ON s.retail_com_id = r.id
            WHERE r.crawl_strdatetime::timestamp >= %s AND r.crawl_strdatetime::timestamp < %s
            GROUP BY r.account_name, period
            ORDER BY r.account_name, period
        """, (start_time, end_time))
        hhp_analyzed_details = {f"{row[0]}_{row[1]}": row[2] for row in cursor.fetchall()}

        # HHP 상세 데이터 조합
        hhp_details = []
        for retailer in RETAILERS:
            for period in ['오전', '오후']:
                key = f"{retailer}_{period}"
                target = hhp_target_details.get(key, 0)
                analyzed = hhp_analyzed_details.get(key, 0)
                rate = round((analyzed / target * 100), 1) if target > 0 else 0

                if target == 0:
                    status = 'PENDING'
                elif rate >= 100:
                    status = 'OK'
                elif rate >= 90:
                    status = 'WARNING'
                else:
                    status = 'CRITICAL'

                hhp_details.append({
                    'retailer': retailer.capitalize(),
                    'period': period,
                    'target': target,
                    'analyzed': analyzed,
                    'rate': rate,
                    'status': status
                })

        hhp_rate = round((hhp_analyzed / hhp_target * 100), 1) if hhp_target > 0 else 0
        if hhp_target == 0:
            hhp_status = 'PENDING'
        elif hhp_rate >= 100:
            hhp_status = 'OK'
        elif hhp_rate >= 90:
            hhp_status = 'WARNING'
        else:
            hhp_status = 'CRITICAL'

        results['hhp'] = {
            'target': hhp_target,
            'analyzed': hhp_analyzed,
            'rate': hhp_rate,
            'status': hhp_status,
            'details': hhp_details
        }

        cursor.close()
        conn.close()

    except Exception as e:
        results['error'] = str(e)

    return JsonResponse(results)
