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


def check_retailer_data(rows, category='TV'):
    """
    리테일러별 데이터 검증
    Returns: (retailer_details, total_count, all_ok)

    rows 형식:
    - TV: (account_name, cnt, main_count, bsr_count, promotion_count)
    - HHP: (account_name, cnt, main_count, bsr_count, trend_count)
    """
    retailer_counts = {r.lower(): {'count': 0, 'main': 0, 'bsr': 0, 'extra': 0} for r in RETAILERS}

    # 수집된 데이터 카운트
    for row in rows:
        retailer_name = row[0].lower() if row[0] else ''
        count = row[1]
        if retailer_name in retailer_counts:
            retailer_counts[retailer_name] = {
                'count': count,
                'main': row[2] if len(row) > 2 else 0,
                'bsr': row[3] if len(row) > 3 else 0,
                'extra': row[4] if len(row) > 4 else 0  # TV: promotion_rank (Bestbuy만), HHP: trend_rank
            }

    retailer_details = []
    total_count = 0
    statuses = []

    for retailer in RETAILERS:
        data = retailer_counts[retailer]
        count = data['count']
        total_count += count

        # 상태 판정: 250 이상 = OK, 200~249 = WARNING, 200 미만 = CRITICAL
        if count >= OK_THRESHOLD:
            status = 'OK'
        elif count >= WARNING_THRESHOLD:
            status = 'WARNING'
        else:
            status = 'CRITICAL'

        statuses.append(status)

        # 수집 항목 정보 구성 (카테고리 및 리테일러에 따라 다름)
        if category == 'TV':
            # TV: Amazon, Walmart는 main_rank, bsr_rank만 / Bestbuy는 promotion_position
            if retailer == 'bestbuy':
                items = [
                    {'name': 'Main Rank', 'count': data['main']},
                    {'name': 'BSR Rank', 'count': data['bsr']},
                    {'name': 'Promotion Position', 'count': data['extra']}
                ]
            else:
                items = [
                    {'name': 'Main Rank', 'count': data['main']},
                    {'name': 'BSR Rank', 'count': data['bsr']}
                ]
        else:
            # HHP: Amazon, Walmart는 main_rank, bsr_rank만 / Bestbuy는 trend_rank
            if retailer == 'bestbuy':
                items = [
                    {'name': 'Main Rank', 'count': data['main']},
                    {'name': 'BSR Rank', 'count': data['bsr']},
                    {'name': 'Trend Rank', 'count': data['extra']}
                ]
            else:
                items = [
                    {'name': 'Main Rank', 'count': data['main']},
                    {'name': 'BSR Rank', 'count': data['bsr']}
                ]

        retailer_details.append({
            'retailer': retailer.capitalize(),
            'count': count,
            'expected': EXPECTED_PER_RETAILER,
            'ok_threshold': OK_THRESHOLD,
            'warning_threshold': WARNING_THRESHOLD,
            'status': status,
            'items': items
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

        # 현재 시간 기준 상태 판단
        now = datetime.now()
        now_hour = now.hour

        # 오전 수집: KST 09:00~14:00 (약 5시간)
        # 오후 수집: KST 21:00~02:00 (다음날, 약 5시간)
        #
        # 상태:
        # - PENDING (대기중): 수집 시간 도래 전
        # - COLLECTING (수집중): 수집 진행 중
        # - OK/WARNING/CRITICAL: 수집 완료 후 결과

        # 조회 날짜가 오늘인 경우만 시간 체크
        if target_date == today:
            # 오전 상태 판단: 09시 이전 대기중, 09~14시 수집중, 14시 이후 결과
            if now_hour < 9:
                am_status = 'PENDING'
            elif now_hour < 14:
                am_status = 'COLLECTING'
            else:
                am_status = None

            # 오후 상태 판단: 21시 이전 대기중, 21~02시(다음날) 수집중
            # 02시 이후는 다음날이므로 오늘 날짜 기준으로는 항상 수집중 또는 대기중
            if now_hour < 2:
                # 새벽 0~2시: 전날 오후 수집이 진행 중 (하지만 이건 전날 데이터)
                # 오늘 오후 수집은 아직 대기중
                pm_status = 'PENDING'
            elif now_hour < 21:
                pm_status = 'PENDING'
            else:
                pm_status = 'COLLECTING'
        elif target_date == today - timedelta(days=1):
            # 전일자 조회: 오전은 결과, 오후는 새벽 2시 이전이면 수집중
            am_status = None
            if now_hour < 2:
                pm_status = 'COLLECTING'  # 전날 오후 수집이 아직 진행 중
            else:
                pm_status = None
        else:
            # 그 외 과거 날짜는 모두 결과 표시
            am_status = None
            pm_status = None

        # 이전 코드와의 호환성을 위해 pending 변수 유지
        am_pending = (am_status in ['PENDING', 'COLLECTING'])
        pm_pending = (pm_status in ['PENDING', 'COLLECTING'])

        time_slots = [
            {
                'name': '오전',
                'start': f'{target_date} 00:00:00',
                'end': f'{target_date} 12:00:00',
                'utc_time': f'{target_date} 00:00',
                'kr_time': f'{target_date} 09:00',
                'is_pending': am_pending,
                'time_status': am_status  # PENDING, COLLECTING, or None
            },
            {
                'name': '오후',
                'start': f'{target_date} 12:00:00',
                'end': f'{next_day} 00:00:00',
                'utc_time': f'{target_date} 12:00',
                'kr_time': f'{target_date} 21:00',
                'is_pending': pm_pending,
                'time_status': pm_status  # PENDING, COLLECTING, or None
            },
        ]

        # ============================================================
        # TV Retail 검증 (통합)
        # ============================================================
        tv_time_slots = []
        tv_total_count = 0
        tv_slot_statuses = []

        for slot in time_slots:
            # TV는 main_rank, bsr_rank, promotion_position (Bestbuy만) 수집
            cursor.execute("""
                SELECT account_name,
                       COUNT(*) as cnt,
                       COUNT(CASE WHEN main_rank IS NOT NULL THEN 1 END) as main_count,
                       COUNT(CASE WHEN bsr_rank IS NOT NULL THEN 1 END) as bsr_count,
                       COUNT(CASE WHEN promotion_position IS NOT NULL THEN 1 END) as promotion_count
                FROM tv_retail_com
                WHERE crawl_datetime::timestamp >= %s
                AND crawl_datetime::timestamp < %s
                GROUP BY account_name
            """, (slot['start'], slot['end']))

            rows = cursor.fetchall()

            if slot['is_pending']:
                # time_status가 COLLECTING이면 수집중, 아니면 대기중
                slot_display_status = slot['time_status'] if slot['time_status'] else 'PENDING'
                # 수집중일 때도 현재까지 수집된 데이터 표시
                retailer_details, total, _ = check_retailer_data(rows)
                tv_time_slots.append({
                    'name': slot['name'],
                    'utc_time': slot['utc_time'],
                    'kr_time': slot['kr_time'],
                    'total': total,
                    'expected': EXPECTED_PER_RETAILER * len(RETAILERS),
                    'status': slot_display_status,
                    'retailers': retailer_details  # 수집중에도 리테일러 데이터 표시
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
        # COLLECTING 상태가 있으면 전체도 COLLECTING
        tv_has_collecting = any(s['status'] == 'COLLECTING' for s in tv_time_slots)
        tv_all_pending = all(s['status'] == 'PENDING' for s in tv_time_slots)

        if 'CRITICAL' in tv_slot_statuses:
            tv_overall_status = 'CRITICAL'
        elif 'WARNING' in tv_slot_statuses:
            tv_overall_status = 'WARNING'
        elif not tv_slot_statuses and tv_has_collecting:
            tv_overall_status = 'COLLECTING'
        elif not tv_slot_statuses and tv_all_pending:
            tv_overall_status = 'PENDING'
        elif not tv_slot_statuses:
            tv_overall_status = 'PENDING'
        else:
            tv_overall_status = 'OK'

        # 활성 슬롯 수 계산 (PENDING, COLLECTING 제외)
        tv_active_slots = len([s for s in tv_time_slots if s['status'] not in ['PENDING', 'COLLECTING']])
        tv_ok_slots = len([s for s in tv_time_slots if s['status'] == 'OK'])

        # TV Retail 데이터 (나중에 통합용으로 저장)
        tv_retail_data = {
            'name': 'TV',
            'total': tv_total_count,
            'expected': EXPECTED_PER_RETAILER * len(RETAILERS) * tv_active_slots,
            'status': tv_overall_status,
            'time_slots': tv_time_slots
        }

        # ============================================================
        # HHP Retail 검증 (통합)
        # ============================================================
        hhp_time_slots = []
        hhp_total_count = 0
        hhp_slot_statuses = []

        for slot in time_slots:
            # HHP도 main_rank, bsr_rank, trend_rank 수집
            cursor.execute("""
                SELECT account_name,
                       COUNT(*) as cnt,
                       COUNT(CASE WHEN main_rank IS NOT NULL THEN 1 END) as main_count,
                       COUNT(CASE WHEN bsr_rank IS NOT NULL THEN 1 END) as bsr_count,
                       COUNT(CASE WHEN trend_rank IS NOT NULL THEN 1 END) as trend_count
                FROM hhp_retail_com
                WHERE crawl_strdatetime::timestamp >= %s
                AND crawl_strdatetime::timestamp < %s
                GROUP BY account_name
            """, (slot['start'], slot['end']))

            rows = cursor.fetchall()

            if slot['is_pending']:
                # time_status가 COLLECTING이면 수집중, 아니면 대기중
                slot_display_status = slot['time_status'] if slot['time_status'] else 'PENDING'
                # 수집중일 때도 현재까지 수집된 데이터 표시
                retailer_details, total, _ = check_retailer_data(rows, category='HHP')
                hhp_time_slots.append({
                    'name': slot['name'],
                    'utc_time': slot['utc_time'],
                    'kr_time': slot['kr_time'],
                    'total': total,
                    'expected': EXPECTED_PER_RETAILER * len(RETAILERS),
                    'status': slot_display_status,
                    'retailers': retailer_details  # 수집중에도 리테일러 데이터 표시
                })
            else:
                retailer_details, total, slot_status = check_retailer_data(rows, category='HHP')
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
        # COLLECTING 상태가 있으면 전체도 COLLECTING
        hhp_has_collecting = any(s['status'] == 'COLLECTING' for s in hhp_time_slots)
        hhp_all_pending = all(s['status'] == 'PENDING' for s in hhp_time_slots)

        if 'CRITICAL' in hhp_slot_statuses:
            hhp_overall_status = 'CRITICAL'
        elif 'WARNING' in hhp_slot_statuses:
            hhp_overall_status = 'WARNING'
        elif not hhp_slot_statuses and hhp_has_collecting:
            hhp_overall_status = 'COLLECTING'
        elif not hhp_slot_statuses and hhp_all_pending:
            hhp_overall_status = 'PENDING'
        elif not hhp_slot_statuses:
            hhp_overall_status = 'PENDING'
        else:
            hhp_overall_status = 'OK'

        # 활성 슬롯 수 계산 (PENDING, COLLECTING 제외)
        hhp_active_slots = len([s for s in hhp_time_slots if s['status'] not in ['PENDING', 'COLLECTING']])
        hhp_ok_slots = len([s for s in hhp_time_slots if s['status'] == 'OK'])

        # HHP Retail 데이터
        hhp_retail_data = {
            'name': 'HHP',
            'total': hhp_total_count,
            'expected': EXPECTED_PER_RETAILER * len(RETAILERS) * hhp_active_slots,
            'status': hhp_overall_status,
            'time_slots': hhp_time_slots
        }

        # Retail 통합 (TV + HHP)
        total_retail_count = tv_total_count + hhp_total_count
        total_retail_expected = (tv_active_slots + hhp_active_slots) * EXPECTED_PER_RETAILER * len(RETAILERS)

        # 통합 상태 결정 (둘 중 더 나쁜 상태)
        status_priority = {'OK': 0, 'WARNING': 1, 'COLLECTING': 2, 'CRITICAL': 3, 'PENDING': 4}
        tv_priority = status_priority.get(tv_overall_status, 0)
        hhp_priority = status_priority.get(hhp_overall_status, 0)

        if tv_priority >= hhp_priority:
            total_retail_status = tv_overall_status
        else:
            total_retail_status = hhp_overall_status

        # 정상 카테고리 수 계산
        retail_ok_count = sum(1 for s in [tv_overall_status, hhp_overall_status] if s == 'OK')

        # 수집 시간 정보 (오전/오후 공통)
        retail_time_info = {
            'am': {'utc': '00:00', 'kst': '09:00'},
            'pm': {'utc': '12:00', 'kst': '21:00'}
        }

        results['checks'].append({
            'name': 'Retail',
            'description': f'{retail_ok_count}/2 카테고리 정상',
            'actual': total_retail_count,
            'expected_min': total_retail_expected,
            'status': total_retail_status,
            'check_type': 'retail',
            'time_info': retail_time_info,
            'categories': [tv_retail_data, hhp_retail_data]
        })

        # ============================================================
        # TV Sentiment 검증
        # ============================================================
        # Sentiment 분석은 다음날 KST 10시(UTC 01시)에 실행됨
        # 분석 소요시간: 약 4시간 (KST 10시~14시)
        #
        # 상태 판단:
        # - 조회날짜가 오늘 이상: PENDING (아직 분석 대상 아님)
        # - 조회날짜가 전일자이고 현재 10시 이전: PENDING (분석 시작 전)
        # - 조회날짜가 전일자이고 현재 10시~14시: ANALYZING (분석중)
        # - 조회날짜가 전일자이고 현재 14시 이후: 결과 표시
        # - 그 외 과거: 결과 표시

        if target_date >= today:
            sentiment_status = 'PENDING'
        elif target_date == today - timedelta(days=1):
            # 전일자 조회: 오늘 시간 기준으로 판단
            if now_hour < 10:
                sentiment_status = 'PENDING'
            elif now_hour < 14:
                sentiment_status = 'ANALYZING'
            else:
                sentiment_status = None  # 결과 표시
        else:
            sentiment_status = None  # 과거 데이터는 결과 표시

        sentiment_pending = (sentiment_status in ['PENDING', 'ANALYZING'])

        # TV 분석 대상 (로그 테이블에서 스냅샷 조회)
        cursor.execute("""
            SELECT COALESCE(SUM(target_count), 0)
            FROM retail_sentiment_analysis_log
            WHERE category = 'TV' AND analysis_date = %s
        """, (target_date,))
        tv_sentiment_target = cursor.fetchone()[0] or 0

        # TV 분석 완료 (실제 sentiment 테이블에서 조회)
        cursor.execute("""
            SELECT COUNT(*)
            FROM tv_retail_sentiment s
            JOIN tv_retail_com r ON s.retail_com_id = r.id
            WHERE r.crawl_datetime::timestamp >= %s AND r.crawl_datetime::timestamp < %s
        """, (f'{target_date} 00:00:00', f'{next_day} 00:00:00'))
        tv_sentiment_analyzed = cursor.fetchone()[0] or 0

        # TV 리테일러별/시간대별 대상 (로그 테이블에서 조회)
        cursor.execute("""
            SELECT retailer, period, target_count
            FROM retail_sentiment_analysis_log
            WHERE category = 'TV' AND analysis_date = %s
        """, (target_date,))
        tv_sent_target_details = {f"{row[0]}_{row[1]}": row[2] for row in cursor.fetchall()}

        # TV 리테일러별/시간대별 분석완료 (실제 테이블에서 조회)
        cursor.execute("""
            SELECT
                LOWER(r.account_name),
                CASE WHEN EXTRACT(HOUR FROM r.crawl_datetime::timestamp) < 12 THEN '오전' ELSE '오후' END as period,
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

                # 상태 판단: 100%면 분석완료(OK), 아니면 시간대 상태 따름
                if sentiment_status == 'PENDING':
                    status = 'PENDING'
                elif target == 0:
                    status = 'PENDING'
                elif rate >= 100:
                    status = 'OK'  # 100%면 분석완료
                elif sentiment_status == 'ANALYZING':
                    status = 'ANALYZING'  # 분석중이면서 100% 미만
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
            # 슬롯 상태 판단: 100%면 분석완료(OK), 아니면 시간대 상태 따름
            if sentiment_status == 'PENDING':
                slot_status = 'PENDING'
            elif slot_target == 0:
                slot_status = 'PENDING'
            elif slot_rate >= 100:
                slot_status = 'OK'  # 100%면 분석완료
            elif sentiment_status == 'ANALYZING':
                slot_status = 'ANALYZING'  # 분석중이면서 100% 미만
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
        # 전체 상태 판단: 100%면 분석완료(OK), 아니면 시간대 상태 따름
        if sentiment_status == 'PENDING':
            tv_sentiment_status = 'PENDING'
        elif tv_sentiment_target == 0:
            tv_sentiment_status = 'PENDING'
        elif tv_sentiment_rate >= 100:
            tv_sentiment_status = 'OK'  # 100%면 분석완료
        elif sentiment_status == 'ANALYZING':
            tv_sentiment_status = 'ANALYZING'  # 분석중이면서 100% 미만
        elif tv_sentiment_rate >= 90:
            tv_sentiment_status = 'WARNING'
        else:
            tv_sentiment_status = 'CRITICAL'

        # TV Sentiment 데이터 (나중에 통합용으로 저장)
        tv_sentiment_data = {
            'name': 'TV',
            'target': tv_sentiment_target,
            'analyzed': tv_sentiment_analyzed,
            'rate': tv_sentiment_rate,
            'status': tv_sentiment_status,
            'time_slots': tv_sentiment_time_slots
        }

        # ============================================================
        # HHP Sentiment 검증
        # ============================================================
        # HHP 분석 대상 (로그 테이블에서 스냅샷 조회)
        cursor.execute("""
            SELECT COALESCE(SUM(target_count), 0)
            FROM retail_sentiment_analysis_log
            WHERE category = 'HHP' AND analysis_date = %s
        """, (target_date,))
        hhp_sentiment_target = cursor.fetchone()[0] or 0

        # HHP 분석 완료 (실제 sentiment 테이블에서 조회)
        cursor.execute("""
            SELECT COUNT(*)
            FROM hhp_retail_sentiment s
            JOIN hhp_retail_com r ON s.retail_com_id = r.id
            WHERE r.crawl_strdatetime::timestamp >= %s AND r.crawl_strdatetime::timestamp < %s
        """, (f'{target_date} 00:00:00', f'{next_day} 00:00:00'))
        hhp_sentiment_analyzed = cursor.fetchone()[0] or 0

        # HHP 리테일러별/시간대별 대상 (로그 테이블에서 조회)
        cursor.execute("""
            SELECT retailer, period, target_count
            FROM retail_sentiment_analysis_log
            WHERE category = 'HHP' AND analysis_date = %s
        """, (target_date,))
        hhp_sent_target_details = {f"{row[0]}_{row[1]}": row[2] for row in cursor.fetchall()}

        # HHP 리테일러별/시간대별 분석완료 (실제 테이블에서 조회)
        cursor.execute("""
            SELECT
                LOWER(r.account_name),
                CASE WHEN EXTRACT(HOUR FROM r.crawl_strdatetime::timestamp) < 12 THEN '오전' ELSE '오후' END as period,
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

                # 상태 판단: 100%면 분석완료(OK), 아니면 시간대 상태 따름
                if sentiment_status == 'PENDING':
                    status = 'PENDING'
                elif target == 0:
                    status = 'PENDING'
                elif rate >= 100:
                    status = 'OK'  # 100%면 분석완료
                elif sentiment_status == 'ANALYZING':
                    status = 'ANALYZING'  # 분석중이면서 100% 미만
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
            # 슬롯 상태 판단: 100%면 분석완료(OK), 아니면 시간대 상태 따름
            if sentiment_status == 'PENDING':
                slot_status = 'PENDING'
            elif slot_target == 0:
                slot_status = 'PENDING'
            elif slot_rate >= 100:
                slot_status = 'OK'  # 100%면 분석완료
            elif sentiment_status == 'ANALYZING':
                slot_status = 'ANALYZING'  # 분석중이면서 100% 미만
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
        # 전체 상태 판단: 100%면 분석완료(OK), 아니면 시간대 상태 따름
        if sentiment_status == 'PENDING':
            hhp_sentiment_status = 'PENDING'
        elif hhp_sentiment_target == 0:
            hhp_sentiment_status = 'PENDING'
        elif hhp_sentiment_rate >= 100:
            hhp_sentiment_status = 'OK'  # 100%면 분석완료
        elif sentiment_status == 'ANALYZING':
            hhp_sentiment_status = 'ANALYZING'  # 분석중이면서 100% 미만
        elif hhp_sentiment_rate >= 90:
            hhp_sentiment_status = 'WARNING'
        else:
            hhp_sentiment_status = 'CRITICAL'

        # HHP Sentiment 데이터
        hhp_sentiment_data = {
            'name': 'HHP',
            'target': hhp_sentiment_target,
            'analyzed': hhp_sentiment_analyzed,
            'rate': hhp_sentiment_rate,
            'status': hhp_sentiment_status,
            'time_slots': hhp_sentiment_time_slots
        }

        # Sentiment 통합 (TV + HHP)
        total_sentiment_target = tv_sentiment_target + hhp_sentiment_target
        total_sentiment_analyzed = tv_sentiment_analyzed + hhp_sentiment_analyzed
        total_sentiment_rate = round((total_sentiment_analyzed / total_sentiment_target * 100), 1) if total_sentiment_target > 0 else 0

        # 통합 상태 결정 (둘 중 더 나쁜 상태)
        status_priority = {'OK': 0, 'WARNING': 1, 'ANALYZING': 2, 'CRITICAL': 3, 'PENDING': 4}
        if total_sentiment_target == 0:
            total_sentiment_status = 'PENDING'
        elif sentiment_status == 'PENDING':
            total_sentiment_status = 'PENDING'
        elif total_sentiment_rate >= 100:
            # 100%면 시간에 관계없이 결과 표시
            total_sentiment_status = 'OK'
        elif sentiment_status == 'ANALYZING':
            total_sentiment_status = 'ANALYZING'
        else:
            tv_priority = status_priority.get(tv_sentiment_status, 0)
            hhp_priority = status_priority.get(hhp_sentiment_status, 0)
            if tv_priority >= hhp_priority:
                total_sentiment_status = tv_sentiment_status
            else:
                total_sentiment_status = hhp_sentiment_status

        # 정상 카테고리 수 계산
        sentiment_ok_count = sum(1 for s in [tv_sentiment_status, hhp_sentiment_status] if s == 'OK')

        results['checks'].append({
            'name': 'Retail 감성분석',
            'description': f'{sentiment_ok_count}/2 카테고리 정상',
            'actual': total_sentiment_analyzed,
            'target': total_sentiment_target,
            'rate': total_sentiment_rate,
            'status': total_sentiment_status,
            'check_type': 'sentiment',
            'utc_time': f'{next_day} 01:00',
            'kr_time': f'{next_day} 10:00',
            'categories': [tv_sentiment_data, hhp_sentiment_data]
        })

        # ============================================================
        # Consumer (YouTube) 검증
        # ============================================================
        # 기대값(7일 평균) 대비 수집률 기준 (Sentiment와 동일)
        # 기준: 100% 이상 = OK, 90~99% = WARNING, 90% 미만 = CRITICAL
        #
        # 수집 시간: 미국시간 12PM = 한국시간 21시
        # 수집 소요시간: 약 1시간 (21시 ~ 22시)
        # 26일 실행 → 26일 데이터 수집
        #
        # 상태 판단:
        # - 오늘 데이터 조회 + 21시 이전: PENDING (대기중)
        # - 오늘 데이터 조회 + 21시~22시: COLLECTING (수집중)
        # - 오늘 데이터 조회 + 22시 이후: 결과 표시
        # - 과거 데이터: 결과 표시

        if target_date == today:
            if now_hour < 21:
                youtube_status = 'PENDING'
            elif now_hour < 22:
                youtube_status = 'COLLECTING'
            else:
                youtube_status = None  # 결과 표시
        else:
            youtube_status = None  # 과거 데이터는 결과 표시

        youtube_pending = (youtube_status in ['PENDING', 'COLLECTING'])

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

        # 기대건수: 활성 키워드 수 (status='active')
        cursor.execute("""
            SELECT category, COUNT(*) as keyword_count
            FROM youtube_keywords
            WHERE status = 'active'
            GROUP BY category
        """)
        youtube_expected_rows = cursor.fetchall()
        youtube_expected_map = {row[0]: row[1] for row in youtube_expected_rows}

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

            # 기대건수: 활성 키워드 수
            expected = youtube_expected_map.get(category, 0)
            # 7일 평균
            avg_data = youtube_avg.get(category, {'avg_video': 0, 'avg_comment': 0})
            avg_7day = avg_data['avg_video']

            # 수집률 계산 (기대건수 기준)
            if expected > 0:
                rate = (log_count / expected) * 100
            else:
                rate = 100 if log_count > 0 else 0

            # 상태 판정: 시간대 상태 + 결과 기준
            if youtube_status == 'PENDING':
                status = 'PENDING'
            elif youtube_status == 'COLLECTING':
                # 수집중일 때 100%면 완료, 아니면 수집중
                if rate >= 100:
                    status = 'OK'
                else:
                    status = 'COLLECTING'
            elif expected == 0:
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
                'expected': expected,  # 기대건수 (활성 키워드 수)
                'avg_7day': round(avg_7day),  # 7일 평균
                'rate': round(rate, 1),
                'status': status
            })

        # YouTube 전체 상태
        if youtube_total_expected > 0:
            youtube_overall_rate = (youtube_total_actual / youtube_total_expected) * 100
        else:
            youtube_overall_rate = 100 if youtube_total_actual > 0 else 0

        # 전체 상태 판정: 시간대 상태 + 결과 기준
        if youtube_status == 'PENDING':
            youtube_overall_status = 'PENDING'
        elif youtube_status == 'COLLECTING':
            # 수집중일 때 100%면 완료, 아니면 수집중
            if youtube_overall_rate >= 100:
                youtube_overall_status = 'OK'
            else:
                youtube_overall_status = 'COLLECTING'
        elif youtube_total_expected == 0:
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

        # Market Trend 카테고리별 상세 데이터 (TV/HHP별로 그룹화)
        market_total_collected = 0
        market_total_expected = 0

        # TV, HHP 각각의 데이터 구성
        tv_market_items = []
        tv_market_total = 0
        tv_market_expected = 0
        tv_market_statuses = []

        hhp_market_items = []
        hhp_market_total = 0
        hhp_market_expected = 0
        hhp_market_statuses = []

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

            market_total_collected += collected
            market_total_expected += expected

            item_data = {
                'name': content_type,
                'collected': collected,
                'expected': expected,
                'avg': avg,
                'rate': round(rate, 1),
                'status': status
            }

            if product_line == 'TV':
                tv_market_items.append(item_data)
                tv_market_total += collected
                tv_market_expected += expected
                tv_market_statuses.append(status)
            else:
                hhp_market_items.append(item_data)
                hhp_market_total += collected
                hhp_market_expected += expected
                hhp_market_statuses.append(status)

        # Event, News 순서로 정렬
        tv_market_items.sort(key=lambda x: content_order.get(x['name'], 99))
        hhp_market_items.sort(key=lambda x: content_order.get(x['name'], 99))

        # TV 전체 상태 계산
        if tv_market_expected > 0:
            tv_market_rate = (tv_market_total / tv_market_expected) * 100
        else:
            tv_market_rate = 0 if tv_market_total == 0 else 100

        if market_pending:
            tv_market_status = 'PENDING'
        elif tv_market_expected == 0:
            tv_market_status = 'PENDING'
        elif tv_market_rate >= 100:
            tv_market_status = 'OK'
        elif tv_market_rate >= 90:
            tv_market_status = 'WARNING'
        else:
            tv_market_status = 'CRITICAL'

        # HHP 전체 상태 계산
        if hhp_market_expected > 0:
            hhp_market_rate = (hhp_market_total / hhp_market_expected) * 100
        else:
            hhp_market_rate = 0 if hhp_market_total == 0 else 100

        if market_pending:
            hhp_market_status = 'PENDING'
        elif hhp_market_expected == 0:
            hhp_market_status = 'PENDING'
        elif hhp_market_rate >= 100:
            hhp_market_status = 'OK'
        elif hhp_market_rate >= 90:
            hhp_market_status = 'WARNING'
        else:
            hhp_market_status = 'CRITICAL'

        # 카테고리 데이터 구성 (Retail/Sentiment와 동일한 구조)
        tv_market_data = {
            'name': 'TV',
            'total': tv_market_total,
            'expected': tv_market_expected,
            'rate': round(tv_market_rate, 1),
            'status': tv_market_status,
            'items': tv_market_items
        }

        hhp_market_data = {
            'name': 'HHP',
            'total': hhp_market_total,
            'expected': hhp_market_expected,
            'rate': round(hhp_market_rate, 1),
            'status': hhp_market_status,
            'items': hhp_market_items
        }

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

        market_ok_count = sum(1 for s in [tv_market_status, hhp_market_status] if s == 'OK')

        results['checks'].append({
            'name': 'Market Trend',
            'description': f'{market_ok_count}/2 카테고리 정상',
            'actual': market_total_collected,
            'expected': market_total_expected,
            'rate': round(market_overall_rate, 1),
            'status': market_overall_status,
            'check_type': 'market_trend',
            'categories': [tv_market_data, hhp_market_data],
            'utc_time': f'{target_date} 23:00',
            'kr_time': f'{next_day} 08:00'
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
        # 수집 시간: UTC 23:00 = KST 다음날 08:00

        # 한국 시간 기준 수집 상태 판정
        import pytz
        kst = pytz.timezone('Asia/Seoul')
        now_kst = datetime.now(kst)

        # 수집 시작 시간: 분석대상일 다음날 08:00 KST
        demand_collection_start = kst.localize(datetime.combine(target_date + timedelta(days=1), datetime.min.time().replace(hour=8)))
        # 수집 완료 시간: 수집 시작 후 30분
        demand_collection_end = demand_collection_start + timedelta(minutes=30)

        # 상태 판정 플래그
        demand_is_pending = now_kst < demand_collection_start
        demand_collection_done = now_kst >= demand_collection_end

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
        # 수요증감율: 100% = OK, 100% 미만 = CRITICAL
        def calc_demand_status(result_cnt, target_cnt):
            if target_cnt == 0:
                return 0, 'OK' if result_cnt == 0 else 'CRITICAL'
            ratio = result_cnt / target_cnt
            if ratio >= 1.0:  # 100% 이상
                return round(ratio * 100, 1), 'OK'
            else:  # 100% 미만
                return round(ratio * 100, 1), 'CRITICAL'

        # 조회일 결과 (카테고리별)
        demand_categories = []
        demand_is_collecting = False
        for category in sorted(target_demand.keys()):
            target = target_demand.get(category, 0) - excluded_demand.get(category, 0)
            target = max(0, target)  # 음수 방지
            result_cnt = result_demand.get(category, 0)
            completion_pct, base_status = calc_demand_status(result_cnt, target)

            # 시간 기반 상태 판정
            if demand_is_pending:
                status = 'PENDING'
            elif completion_pct >= 100:
                status = 'OK'
            elif demand_collection_done:
                # 수집 시간 경과 후 결과 표시
                status = base_status
            else:
                # 수집 중 (100% 미만이고 30분 미경과)
                status = 'COLLECTING'
                demand_is_collecting = True

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
        demand_rate, _ = calc_demand_status(demand_total_collected, demand_total_target)
        demand_ok_count = len([c for c in demand_categories if c['status'] == 'OK'])

        # 전체 상태 판정 (시간 기반)
        # 수요증감율: 100% = OK, 100% 미만 = CRITICAL
        if demand_is_pending:
            demand_overall_status = 'PENDING'
            demand_description = '대기중 (다음날 08:00 수집 예정)'
        elif demand_rate >= 100:
            demand_overall_status = 'OK'
            demand_description = f'{demand_ok_count}/{len(demand_categories)} 카테고리 정상'
        elif demand_collection_done:
            # 수집 시간 경과 후 결과 표시 (100% 미만은 무조건 CRITICAL)
            demand_overall_status = 'CRITICAL'
            demand_description = f'{demand_ok_count}/{len(demand_categories)} 카테고리 정상'
        else:
            # 수집 중
            demand_overall_status = 'COLLECTING'
            demand_description = f'수집중 ({demand_rate}%)'

        results['checks'].append({
            'name': 'Market 수요증감율',
            'description': demand_description,
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
        # 실행시간: 매주 월요일 (수집은 화요일 03:00 KST)
        # 대상: 9주 이내 이벤트 × 7개 리테일러
        # 기준: 100% = OK, 90%+ = WARNING, 90%- = CRITICAL

        # 조회 날짜가 월요일인지 확인 (0=월요일)
        is_monday = target_date.weekday() == 0

        # 한국 시간 기준 수집 상태 판정
        # 수집 시간: 화요일 03:00 KST (월요일 분석대상일 기준)
        from datetime import timezone
        import pytz
        kst = pytz.timezone('Asia/Seoul')
        now_kst = datetime.now(kst)
        today_kst = now_kst.date()

        # 수집 시작 시간: 분석대상일(월요일) 다음날(화요일) 03:00 KST
        collection_start_datetime = kst.localize(datetime.combine(target_date + timedelta(days=1), datetime.min.time().replace(hour=3)))
        # 수집 완료 시간: 수집 시작 후 30분
        collection_end_datetime = collection_start_datetime + timedelta(minutes=30)

        # 상태 판정
        promo_is_collecting = False
        promo_is_pending = False
        promo_collection_done = False  # 수집 시간 경과 여부

        if is_monday:
            if now_kst < collection_start_datetime:
                # 수집 시작 전 → 대기중
                promo_is_pending = True
            elif now_kst >= collection_end_datetime:
                # 수집 시간 경과 (30분 지남) → 결과 표시
                promo_collection_done = True
            # else: 수집 중 (03:00 ~ 03:30)

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
            elif promo_is_pending:
                status = 'PENDING'
            elif expected == 0:
                status = 'PENDING'
            elif rate >= 100:
                # 100% 완료
                status = 'OK'
                promo_ok_count += 1
            elif promo_collection_done:
                # 수집 시간 경과 (30분 지남) + 100% 미만 → 결과 표시 (WARNING/CRITICAL)
                if rate >= 90:
                    status = 'WARNING'
                else:
                    status = 'CRITICAL'
            else:
                # 수집 중 (100% 미만이고 30분 미경과)
                status = 'COLLECTING'
                promo_is_collecting = True

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
            promo_description = '분석대상일 아님'
        elif promo_is_pending:
            promo_overall_status = 'PENDING'
            promo_description = '대기중 (화요일 03:00 수집 예정)'
        elif promo_expected == 0:
            promo_overall_status = 'PENDING'
            promo_description = '대상 이벤트 없음'
        elif promo_overall_rate >= 100:
            # 100% 완료
            promo_overall_status = 'OK'
            promo_description = f'{promo_ok_count}/{len(PROMO_RETAILERS)} 리테일러 정상'
        elif promo_collection_done:
            # 수집 시간 경과 (30분 지남) + 100% 미만 → 결과 표시
            if promo_overall_rate >= 90:
                promo_overall_status = 'WARNING'
            else:
                promo_overall_status = 'CRITICAL'
            promo_description = f'{promo_ok_count}/{len(PROMO_RETAILERS)} 리테일러 정상'
        else:
            # 수집 중 (100% 미만이고 30분 미경과)
            promo_overall_status = 'COLLECTING'
            promo_description = f'수집중 ({round(promo_overall_rate, 1)}%)'

        results['checks'].append({
            'name': 'Market Promotion',
            'description': promo_description,
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

        # Summary 계산 (화면 섹션 기준 8개)
        # 분석대상일이 아닌 항목은 PENDING으로 처리
        all_statuses = [
            total_retail_status,                                              # Retail
            total_sentiment_status,                                           # Retail 감성분석
            youtube_overall_status,                                           # Consumer (YouTube)
            market_overall_status,                                            # Market Trend
            demand_overall_status,                                            # Market 수요증감율
            comp_overall_status if is_quarter_first else 'PENDING',           # Market Competitor (분기 첫날만)
            event_overall_status if is_first_monday else 'PENDING',           # Market Competitor Event (매월 첫 월요일만)
            promo_overall_status                                              # Market Promotion (is_monday 이미 반영됨)
        ]
        active_statuses = [s for s in all_statuses if s not in ('PENDING', 'COLLECTING', 'ANALYZING')]

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


def retail_summary(request):
    """Retail 상세 현황 API - 리테일러×시간대×페이지타입별 테이블 + NULL 컬럼 현황"""
    date_str = request.GET.get('date')
    product_line = request.GET.get('type', 'tv')  # tv or hhp

    if date_str:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    else:
        target_date = (datetime.now() - timedelta(days=1)).date()

    next_day = target_date + timedelta(days=1)

    # 시간대 정의
    time_slots = [
        {'name': '오전', 'start': f'{target_date} 00:00:00', 'end': f'{target_date} 12:00:00'},
        {'name': '오후', 'start': f'{target_date} 12:00:00', 'end': f'{next_day} 00:00:00'}
    ]

    try:
        conn = get_dx_connection()
        cursor = conn.cursor()

        # 테이블명 및 날짜 필드 결정
        if product_line == 'tv':
            table_name = 'tv_retail_com'
            date_field = 'crawl_datetime::timestamp'
            # TV는 promotion_position (Bestbuy만)
            extra_rank_field = 'promotion_position'
            extra_rank_name = 'Promotion'
        else:
            table_name = 'hhp_retail_com'
            date_field = 'crawl_strdatetime::timestamp'
            # HHP는 trend_rank (Bestbuy만)
            extra_rank_field = 'trend_rank'
            extra_rank_name = 'Trend'

        # 리테일러 목록
        retailers = ['Amazon', 'Bestbuy', 'Walmart']

        # 결과 데이터 구조
        summary_data = []
        null_columns_data = []

        # 리테일러별 컬럼 목록 (Layer 2와 동일 - 전체 컬럼)
        if product_line == 'tv':
            columns_by_retailer = {
                'Amazon': [
                    'item', 'account_name', 'page_type', 'product_url', 'screen_size',
                    'retailer_sku_name', 'count_of_reviews', 'star_rating', 'count_of_star_ratings',
                    'number_of_units_purchased_past_month', 'final_sku_price', 'original_sku_price',
                    'shipping_info', 'available_quantity_for_purchase', 'discount_type', 'sku_popularity',
                    'retailer_membership_discounts', 'rank_1', 'rank_2', 'summarized_review_content',
                    'detailed_review_content', 'main_rank', 'bsr_rank', 'calendar_week', 'crawl_datetime'
                ],
                'Bestbuy': [
                    'item', 'account_name', 'page_type', 'product_url', 'screen_size',
                    'retailer_sku_name', 'final_sku_price', 'original_sku_price', 'savings', 'offer',
                    'pick_up_availability', 'shipping_availability', 'delivery_availability',
                    'count_of_reviews', 'star_rating', 'count_of_star_ratings',
                    'estimated_annual_electricity_use', 'retailer_sku_name_similar', 'top_mentions',
                    'detailed_review_content', 'recommendation_intent', 'promotion_type',
                    'main_rank', 'bsr_rank', 'calendar_week', 'crawl_datetime'
                ],
                'Walmart': [
                    'item', 'account_name', 'page_type', 'product_url', 'screen_size',
                    'retailer_sku_name', 'final_sku_price', 'original_sku_price', 'offer',
                    'pick_up_availability', 'shipping_availability', 'delivery_availability',
                    'sku_status', 'retailer_membership_discounts', 'available_quantity_for_purchase',
                    'inventory_status', 'number_of_ppl_purchased_yesterday', 'number_of_ppl_added_to_carts',
                    'sku_popularity', 'savings', 'discount_type', 'shipping_info', 'count_of_reviews',
                    'star_rating', 'count_of_star_ratings', 'detailed_review_content',
                    'main_rank', 'bsr_rank', 'calendar_week', 'crawl_datetime'
                ]
            }
        else:
            columns_by_retailer = {
                'Amazon': [
                    'country', 'product', 'item', 'account_name', 'page_type', 'product_url', 'main_rank', 'bsr_rank',
                    'retailer_sku_name', 'number_of_units_purchased_past_month', 'final_sku_price', 'original_sku_price',
                    'shipping_info', 'available_quantity_for_purchase', 'discount_type',
                    'count_of_reviews', 'star_rating', 'count_of_star_ratings',
                    'sku_popularity', 'bundle', 'trade_in', 'retailer_membership_discounts', 'rank_1', 'rank_2',
                    'hhp_carrier', 'hhp_storage', 'hhp_color', 'summarized_review_content', 'detailed_review_content',
                    'calendar_week', 'crawl_strdatetime'
                ],
                'Bestbuy': [
                    'country', 'product', 'item', 'account_name', 'page_type', 'main_rank', 'bsr_rank', 'trend_rank', 'product_url',
                    'retailer_sku_name', 'final_sku_price', 'original_sku_price', 'savings', 'offer',
                    'pick_up_availability', 'shipping_availability', 'delivery_availability',
                    'sku_status', 'promotion_type', 'trade_in', 'hhp_carrier', 'hhp_storage', 'hhp_color',
                    'retailer_sku_name_similar', 'top_mentions', 'recommendation_intent',
                    'count_of_reviews', 'star_rating', 'count_of_star_ratings', 'detailed_review_content',
                    'calendar_week', 'crawl_strdatetime'
                ],
                'Walmart': [
                    'item', 'account_name', 'page_type', 'product_url',
                    'retailer_sku_name', 'final_sku_price', 'original_sku_price', 'offer',
                    'pick_up_availability', 'shipping_availability', 'delivery_availability', 'sku_status',
                    'retailer_membership_discounts', 'available_quantity_for_purchase', 'inventory_status',
                    'number_of_ppl_purchased_yesterday', 'number_of_ppl_added_to_carts', 'sku_popularity',
                    'savings', 'discount_type', 'shipping_info', 'count_of_reviews', 'star_rating', 'count_of_star_ratings',
                    'hhp_carrier', 'hhp_storage', 'hhp_color', 'detailed_review_content',
                    'main_rank', 'bsr_rank', 'calendar_week', 'crawl_strdatetime'
                ]
            }

        for retailer in retailers:
            retailer_rows = []
            retailer_null_cols = []
            retailer_total = 0
            check_columns = columns_by_retailer.get(retailer, [])

            for slot in time_slots:
                # 시간대별 페이지타입 카운트
                cursor.execute(f"""
                    SELECT
                        COUNT(CASE WHEN page_type = 'main' OR main_rank IS NOT NULL THEN 1 END) as main_count,
                        COUNT(CASE WHEN page_type = 'bsr' OR bsr_rank IS NOT NULL THEN 1 END) as bsr_count,
                        COUNT(CASE WHEN {extra_rank_field} IS NOT NULL THEN 1 END) as extra_count,
                        COUNT(*) as total
                    FROM {table_name}
                    WHERE {date_field} >= %s
                    AND {date_field} < %s
                    AND LOWER(account_name) = LOWER(%s)
                """, (slot['start'], slot['end'], retailer))

                row = cursor.fetchone()
                main_count = row[0] or 0
                bsr_count = row[1] or 0
                extra_count = row[2] or 0
                total = row[3] or 0

                retailer_rows.append({
                    'time_slot': slot['name'],
                    'main': main_count,
                    'bsr': bsr_count,
                    'extra': extra_count,
                    'extra_name': extra_rank_name,
                    'total': total
                })
                retailer_total += total

                # NULL 컬럼 체크 - Layer 2와 동일한 방식 (COUNT로 한번에 조회)
                if total > 0 and check_columns:
                    count_parts = [f"COUNT({col}) as {col}_cnt" for col in check_columns]
                    query = f"""
                        SELECT {', '.join(count_parts)}
                        FROM {table_name}
                        WHERE {date_field} >= %s
                        AND {date_field} < %s
                        AND LOWER(account_name) = LOWER(%s)
                    """
                    cursor.execute(query, (slot['start'], slot['end'], retailer))
                    count_row = cursor.fetchone()
                    if count_row:
                        # COUNT가 0인 컬럼 = 전체가 NULL인 컬럼
                        null_cols = [col for col, cnt in zip(check_columns, count_row) if cnt == 0]
                        if null_cols:
                            retailer_null_cols.append({
                                'time_slot': slot['name'],
                                'null_columns': null_cols
                            })

            summary_data.append({
                'retailer': retailer,
                'rows': retailer_rows,
                'total': retailer_total
            })

            if retailer_null_cols:
                null_columns_data.append({
                    'retailer': retailer,
                    'time_slots': retailer_null_cols
                })

        # 전체 합계 계산
        grand_total = sum(r['total'] for r in summary_data)
        am_total = sum(r['rows'][0]['total'] for r in summary_data if r['rows'])
        pm_total = sum(r['rows'][1]['total'] for r in summary_data if len(r['rows']) > 1)

        cursor.close()
        conn.close()

        return JsonResponse({
            'date': str(target_date),
            'product_line': product_line.upper(),
            'extra_rank_name': extra_rank_name,
            'summary': summary_data,
            'null_columns': null_columns_data,
            'totals': {
                'grand_total': grand_total,
                'am_total': am_total,
                'pm_total': pm_total
            }
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

        # TV 분석 대상 (로그 테이블에서 스냅샷 조회)
        cursor.execute("""
            SELECT COALESCE(SUM(target_count), 0)
            FROM retail_sentiment_analysis_log
            WHERE category = 'TV' AND analysis_date = %s
        """, (target_date,))
        tv_target = cursor.fetchone()[0] or 0

        # TV 분석 완료 (실제 sentiment 테이블에서 조회)
        cursor.execute("""
            SELECT COUNT(*)
            FROM tv_retail_sentiment s
            JOIN tv_retail_com r ON s.retail_com_id = r.id
            WHERE r.crawl_datetime::timestamp >= %s AND r.crawl_datetime::timestamp < %s
        """, (start_time, end_time))
        tv_analyzed = cursor.fetchone()[0] or 0

        # TV 리테일러별/시간대별 대상 (로그 테이블에서 조회)
        cursor.execute("""
            SELECT retailer, period, target_count
            FROM retail_sentiment_analysis_log
            WHERE category = 'TV' AND analysis_date = %s
        """, (target_date,))
        tv_target_details = {f"{row[0]}_{row[1]}": row[2] for row in cursor.fetchall()}

        # TV 리테일러별/시간대별 분석완료 (실제 테이블에서 조회)
        cursor.execute("""
            SELECT
                LOWER(r.account_name),
                CASE WHEN EXTRACT(HOUR FROM r.crawl_datetime::timestamp) < 12 THEN '오전' ELSE '오후' END as period,
                COUNT(*) as analyzed_count
            FROM tv_retail_sentiment s
            JOIN tv_retail_com r ON s.retail_com_id = r.id
            WHERE r.crawl_datetime::timestamp >= %s AND r.crawl_datetime::timestamp < %s
            GROUP BY LOWER(r.account_name), period
            ORDER BY LOWER(r.account_name), period
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

        # HHP 분석 대상 (로그 테이블에서 스냅샷 조회)
        cursor.execute("""
            SELECT COALESCE(SUM(target_count), 0)
            FROM retail_sentiment_analysis_log
            WHERE category = 'HHP' AND analysis_date = %s
        """, (target_date,))
        hhp_target = cursor.fetchone()[0] or 0

        # HHP 분석 완료 (실제 sentiment 테이블에서 조회)
        cursor.execute("""
            SELECT COUNT(*)
            FROM hhp_retail_sentiment s
            JOIN hhp_retail_com r ON s.retail_com_id = r.id
            WHERE r.crawl_strdatetime::timestamp >= %s AND r.crawl_strdatetime::timestamp < %s
        """, (start_time, end_time))
        hhp_analyzed = cursor.fetchone()[0] or 0

        # HHP 리테일러별/시간대별 대상 (로그 테이블에서 조회)
        cursor.execute("""
            SELECT retailer, period, target_count
            FROM retail_sentiment_analysis_log
            WHERE category = 'HHP' AND analysis_date = %s
        """, (target_date,))
        hhp_target_details = {f"{row[0]}_{row[1]}": row[2] for row in cursor.fetchall()}

        # HHP 리테일러별/시간대별 분석완료 (실제 테이블에서 조회)
        cursor.execute("""
            SELECT
                LOWER(r.account_name),
                CASE WHEN EXTRACT(HOUR FROM r.crawl_strdatetime::timestamp) < 12 THEN '오전' ELSE '오후' END as period,
                COUNT(*) as analyzed_count
            FROM hhp_retail_sentiment s
            JOIN hhp_retail_com r ON s.retail_com_id = r.id
            WHERE r.crawl_strdatetime::timestamp >= %s AND r.crawl_strdatetime::timestamp < %s
            GROUP BY LOWER(r.account_name), period
            ORDER BY LOWER(r.account_name), period
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


def retailer_raw_data(request):
    """
    리테일러별 원본 데이터 조회 API
    - category: TV 또는 HHP
    - retailer: Amazon, Bestbuy, Walmart
    - period: 오전 또는 오후
    - date: 조회 날짜 (YYYY-MM-DD)
    """
    category = request.GET.get('category', 'TV')
    retailer = request.GET.get('retailer', 'Amazon')
    period = request.GET.get('period', '오전')
    date_str = request.GET.get('date')

    if not date_str:
        target_date = (datetime.now() - timedelta(days=1)).date()
    else:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()

    next_day = target_date + timedelta(days=1)

    # 시간대 설정
    if period == '오전':
        start_time = f'{target_date} 00:00:00'
        end_time = f'{target_date} 12:00:00'
    else:
        start_time = f'{target_date} 12:00:00'
        end_time = f'{next_day} 00:00:00'

    results = {
        'category': category,
        'retailer': retailer,
        'period': period,
        'date': str(target_date),
        'columns': [],
        'data': []
    }

    try:
        conn = get_dx_connection()
        cursor = conn.cursor()

        if category == 'TV':
            # TV 컬럼 (BestBuy 기준)
            columns = [
                'id', 'item', 'account_name', 'page_type', 'product_url', 'screen_size',
                'retailer_sku_name', 'final_sku_price', 'original_sku_price', 'savings', 'offer',
                'pick_up_availability', 'shipping_availability', 'delivery_availability',
                'count_of_reviews', 'star_rating', 'count_of_star_ratings',
                'estimated_annual_electricity_use', 'retailer_sku_name_similar', 'top_mentions',
                'detailed_review_content', 'recommendation_intent', 'promotion_type',
                'main_rank', 'bsr_rank', 'calendar_week', 'crawl_datetime'
            ]

            query = f"""
                SELECT {', '.join(columns)}
                FROM tv_retail_com
                WHERE LOWER(account_name) = LOWER(%s)
                AND crawl_datetime >= %s
                AND crawl_datetime < %s
                ORDER BY id DESC
                LIMIT 500
            """
        else:
            # HHP 컬럼
            columns = [
                'id', 'item', 'account_name', 'page_type', 'product_url',
                'retailer_sku_name', 'count_of_reviews', 'star_rating', 'count_of_star_ratings',
                'number_of_units_purchased_past_month', 'final_sku_price', 'original_sku_price',
                'shipping_info', 'available_quantity_for_purchase', 'discount_type',
                'sku_popularity', 'retailer_membership_discounts', 'rank_1', 'rank_2',
                'hhp_carrier', 'hhp_storage', 'hhp_color',
                'summarized_review_content', 'detailed_review_content',
                'main_rank', 'bsr_rank', 'trend_rank', 'calendar_week', 'crawl_strdatetime'
            ]

            query = f"""
                SELECT {', '.join(columns)}
                FROM hhp_retail_com
                WHERE LOWER(account_name) = LOWER(%s)
                AND crawl_strdatetime >= %s
                AND crawl_strdatetime < %s
                ORDER BY id DESC
                LIMIT 500
            """

        cursor.execute(query, (retailer, start_time, end_time))
        rows = cursor.fetchall()

        results['columns'] = columns
        results['total_count'] = len(rows)
        results['data'] = rows

        cursor.close()
        conn.close()

    except Exception as e:
        results['error'] = str(e)

    return JsonResponse(results)


def retailer_columns_info(request):
    """
    TV/HHP 리테일러별 수집 컬럼 정보 API
    """
    # TV 리테일러별 컬럼 정의
    tv_columns = {
        'Amazon': [
            'id', 'item', 'account_name', 'page_type', 'product_url', 'screen_size',
            'retailer_sku_name', 'count_of_reviews', 'star_rating', 'count_of_star_ratings',
            'number_of_units_purchased_past_month', 'final_sku_price', 'original_sku_price',
            'shipping_info', 'available_quantity_for_purchase', 'discount_type', 'sku_popularity',
            'retailer_membership_discounts', 'rank_1', 'rank_2', 'summarized_review_content',
            'detailed_review_content', 'main_rank', 'bsr_rank', 'calendar_week', 'crawl_datetime'
        ],
        'Bestbuy': [
            'id', 'item', 'account_name', 'page_type', 'product_url', 'screen_size',
            'retailer_sku_name', 'final_sku_price', 'original_sku_price', 'savings', 'offer',
            'pick_up_availability', 'shipping_availability', 'delivery_availability',
            'count_of_reviews', 'star_rating', 'count_of_star_ratings',
            'estimated_annual_electricity_use', 'retailer_sku_name_similar', 'top_mentions',
            'detailed_review_content', 'recommendation_intent', 'promotion_type',
            'main_rank', 'bsr_rank', 'calendar_week', 'crawl_datetime'
        ],
        'Walmart': [
            'id', 'item', 'account_name', 'page_type', 'product_url', 'screen_size',
            'retailer_sku_name', 'final_sku_price', 'original_sku_price', 'offer',
            'pick_up_availability', 'shipping_availability', 'delivery_availability',
            'sku_status', 'retailer_membership_discounts', 'available_quantity_for_purchase',
            'inventory_status', 'number_of_ppl_purchased_yesterday', 'number_of_ppl_added_to_carts',
            'sku_popularity', 'savings', 'discount_type', 'shipping_info', 'count_of_reviews',
            'star_rating', 'count_of_star_ratings', 'detailed_review_content',
            'main_rank', 'bsr_rank', 'calendar_week', 'crawl_datetime'
        ]
    }

    # HHP 리테일러별 컬럼 정의
    hhp_columns = {
        'Amazon': [
            'id', 'country', 'product', 'item', 'account_name', 'page_type', 'product_url', 'main_rank', 'bsr_rank',
            'retailer_sku_name', 'number_of_units_purchased_past_month', 'final_sku_price', 'original_sku_price',
            'shipping_info', 'available_quantity_for_purchase', 'discount_type',
            'count_of_reviews', 'star_rating', 'count_of_star_ratings',
            'sku_popularity', 'bundle', 'trade_in', 'retailer_membership_discounts', 'rank_1', 'rank_2',
            'hhp_carrier', 'hhp_storage', 'hhp_color', 'summarized_review_content', 'detailed_review_content',
            'calendar_week', 'crawl_strdatetime'
        ],
        'Bestbuy': [
            'id', 'country', 'product', 'item', 'account_name', 'page_type', 'count_of_reviews',
            'retailer_sku_name', 'product_url', 'star_rating', 'count_of_star_ratings',
            'final_sku_price', 'original_sku_price', 'savings', 'offer',
            'pick_up_availability', 'shipping_availability', 'delivery_availability', 'sku_status',
            'trade_in', 'hhp_carrier', 'hhp_storage', 'hhp_color', 'detailed_review_content', 'top_mentions',
            'recommendation_intent', 'main_rank', 'bsr_rank', 'trend_rank',
            'promotion_type', 'retailer_sku_name_similar', 'calendar_week', 'crawl_strdatetime'
        ],
        'Walmart': [
            'id', 'item', 'account_name', 'page_type', 'product_url',
            'retailer_sku_name', 'final_sku_price', 'original_sku_price', 'offer',
            'pick_up_availability', 'shipping_availability', 'delivery_availability', 'sku_status',
            'retailer_membership_discounts', 'available_quantity_for_purchase', 'inventory_status',
            'number_of_ppl_purchased_yesterday', 'number_of_ppl_added_to_carts',
            'sku_popularity', 'savings', 'discount_type', 'shipping_info',
            'hhp_carrier', 'hhp_storage', 'hhp_color', 'retailer_sku_name_similar', 'detailed_review_content',
            'count_of_reviews', 'star_rating', 'count_of_star_ratings', 'main_rank', 'bsr_rank',
            'calendar_week', 'crawl_strdatetime'
        ]
    }

    # 모든 컬럼 목록 (합집합) - 알파벳 순 정렬
    all_tv_columns = sorted(set(col for cols in tv_columns.values() for col in cols))
    all_hhp_columns = sorted(set(col for cols in hhp_columns.values() for col in cols))

    return JsonResponse({
        'tv': {
            'columns': tv_columns,
            'all_columns': all_tv_columns
        },
        'hhp': {
            'columns': hhp_columns,
            'all_columns': all_hhp_columns
        }
    })


def sentiment_raw_data(request):
    """
    감성분석 원본 데이터 조회 API
    - category: TV 또는 HHP
    - retailer: Amazon, Bestbuy, Walmart
    - period: 오전 또는 오후
    - date: 조회 날짜 (YYYY-MM-DD)
    """
    category = request.GET.get('category', 'TV')
    retailer = request.GET.get('retailer', 'Amazon')
    period = request.GET.get('period', '오전')
    date_str = request.GET.get('date')

    if not date_str:
        target_date = (datetime.now() - timedelta(days=1)).date()
    else:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()

    next_day = target_date + timedelta(days=1)

    # 시간대 설정
    if period == '오전':
        start_time = f'{target_date} 00:00:00'
        end_time = f'{target_date} 12:00:00'
    else:
        start_time = f'{target_date} 12:00:00'
        end_time = f'{next_day} 00:00:00'

    results = {
        'category': category,
        'retailer': retailer,
        'period': period,
        'date': str(target_date),
        'columns': [],
        'data': []
    }

    try:
        conn = get_dx_connection()
        cursor = conn.cursor()

        if category == 'TV':
            # TV 감성분석 데이터 조회
            columns = [
                'id', 'retail_com_id', 'item', 'sentiment_score',
                'final_interpretation', 'created_at', 'batch_id'
            ]

            query = """
                SELECT
                    s.id,
                    s.retail_com_id,
                    r.item,
                    s.sentiment_score,
                    s.final_interpretation,
                    s.created_at,
                    s.batch_id
                FROM tv_retail_sentiment s
                JOIN tv_retail_com r ON s.retail_com_id = r.id
                WHERE LOWER(r.account_name) = LOWER(%s)
                AND r.crawl_datetime >= %s
                AND r.crawl_datetime < %s
                ORDER BY s.id DESC
                LIMIT 500
            """
        else:
            # HHP 감성분석 데이터 조회
            columns = [
                'id', 'retail_com_id', 'item', 'sentiment_score',
                'final_interpretation', 'created_at', 'batch_id'
            ]

            query = """
                SELECT
                    s.id,
                    s.retail_com_id,
                    r.item,
                    s.sentiment_score,
                    s.final_interpretation,
                    s.created_at,
                    s.batch_id
                FROM hhp_retail_sentiment s
                JOIN hhp_retail_com r ON s.retail_com_id = r.id
                WHERE LOWER(r.account_name) = LOWER(%s)
                AND r.crawl_strdatetime >= %s
                AND r.crawl_strdatetime < %s
                ORDER BY s.id DESC
                LIMIT 500
            """

        cursor.execute(query, (retailer, start_time, end_time))
        rows = cursor.fetchall()

        results['columns'] = columns
        results['total_count'] = len(rows)
        results['data'] = rows

        cursor.close()
        conn.close()

    except Exception as e:
        results['error'] = str(e)

    return JsonResponse(results)


def youtube_raw_data(request):
    """
    YouTube 원본 데이터 조회 API
    - category: TV 또는 HHP
    - date: 조회 날짜 (YYYY-MM-DD)
    - data_type: logs, videos, comments (기본: logs)
    """
    category = request.GET.get('category', 'TV')
    date_str = request.GET.get('date')
    data_type = request.GET.get('data_type', 'logs')

    if not date_str:
        target_date = (datetime.now() - timedelta(days=1)).date()
    else:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()

    results = {
        'category': category,
        'date': str(target_date),
        'data_type': data_type,
        'columns': [],
        'data': [],
        'total_count': 0
    }

    try:
        conn = get_dx_connection()
        cursor = conn.cursor()

        if data_type == 'logs':
            # 수집 로그 데이터
            columns = [
                'id', 'keyword', 'category', 'status', 'videos_collected',
                'comments_collected', 'started_at', 'completed_at', 'error_message'
            ]

            query = """
                SELECT
                    l.id,
                    k.keyword,
                    k.category,
                    l.status,
                    l.videos_collected,
                    l.comments_collected,
                    l.started_at,
                    l.completed_at,
                    l.error_message
                FROM youtube_collection_logs l
                LEFT JOIN youtube_keywords k ON l.keyword_id = k.id
                WHERE DATE(l.started_at) = %s
                AND k.category = %s
                ORDER BY l.id DESC
                LIMIT 500
            """
            cursor.execute(query, (target_date, category))

        elif data_type == 'videos':
            # 비디오 데이터 - 모든 컬럼
            columns = [
                'video_id', 'keyword', 'title', 'description', 'published_at',
                'channel_country', 'channel_custom_url', 'channel_subscriber_count', 'channel_video_count',
                'view_count', 'like_count', 'comment_count', 'category_id', 'category',
                'engagement_rate', 'reviewed_brand', 'reviewed_series', 'reviewed_item',
                'product_sentiment_score', 'product_sentiment_score_comment', 'comment_text_summary',
                'created_at'
            ]

            query = """
                SELECT
                    v.video_id,
                    v.keyword,
                    v.title,
                    v.description,
                    v.published_at,
                    v.channel_country,
                    v.channel_custom_url,
                    v.channel_subscriber_count,
                    v.channel_video_count,
                    v.view_count,
                    v.like_count,
                    v.comment_count,
                    v.category_id,
                    v.category,
                    v.engagement_rate,
                    v.reviewed_brand,
                    v.reviewed_series,
                    v.reviewed_item,
                    v.product_sentiment_score,
                    v.product_sentiment_score_comment,
                    v.comment_text_summary,
                    v.created_at
                FROM youtube_videos v
                LEFT JOIN youtube_keywords k ON v.keyword = k.keyword
                WHERE DATE(v.created_at) = %s
                AND k.category = %s
                ORDER BY v.created_at DESC
                LIMIT 500
            """
            cursor.execute(query, (target_date, category))

        elif data_type == 'comments':
            # 댓글 데이터 - 전체 컬럼
            columns = [
                'comment_id', 'video_id', 'comment_type', 'parent_comment_id',
                'comment_text_display', 'like_count', 'reply_count',
                'published_at', 'sentiment_score', 'created_at'
            ]

            query = """
                SELECT DISTINCT
                    c.comment_id,
                    c.video_id,
                    c.comment_type,
                    c.parent_comment_id,
                    c.comment_text_display,
                    c.like_count,
                    c.reply_count,
                    c.published_at,
                    c.sentiment_score,
                    c.created_at
                FROM youtube_comments c
                JOIN youtube_videos v ON c.video_id = v.video_id
                WHERE DATE(c.created_at) = %s
                AND v.keyword IN (SELECT keyword FROM youtube_keywords WHERE category = %s)
                ORDER BY c.created_at DESC
            """
            cursor.execute(query, (target_date, category))

        rows = cursor.fetchall()

        results['columns'] = columns
        results['total_count'] = len(rows)
        results['data'] = rows

        cursor.close()
        conn.close()

    except Exception as e:
        results['error'] = str(e)

    return JsonResponse(results)


def market_trend_raw_data(request):
    """
    Market Trend 원본 데이터 조회 API
    - category: TV 또는 HHP
    - content_type: search_volume, social_trend, news_trend 등
    - date: 조회 날짜 (YYYY-MM-DD)
    """
    category = request.GET.get('category', 'TV')
    content_type = request.GET.get('content_type', '')
    date_str = request.GET.get('date')

    if not date_str:
        target_date = (datetime.now() - timedelta(days=1)).date()
    else:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()

    results = {
        'category': category,
        'content_type': content_type,
        'date': str(target_date),
        'columns': [],
        'data': [],
        'total_count': 0
    }

    try:
        conn = get_dx_connection()
        cursor = conn.cursor()

        # market_trend 테이블 컬럼 (실제 테이블 구조에 맞춤)
        columns = [
            'keyword', 'product_line', 'content_type', 'total_article_number',
            'calendar_week', 'crawl_at_local_time'
        ]

        if content_type:
            query = """
                SELECT
                    t.keyword,
                    m.product_line,
                    m.content_type,
                    t.total_article_number,
                    t.calendar_week,
                    t.crawl_at_local_time
                FROM market_trend t
                INNER JOIN market_mst m ON m.analysis_type = 'trend' AND t.keyword = m.keyword
                WHERE DATE(t.crawl_at_local_time) = %s
                AND m.product_line = %s
                AND m.content_type = %s
                ORDER BY t.crawl_at_local_time DESC
                LIMIT 500
            """
            cursor.execute(query, (target_date, category, content_type))
        else:
            query = """
                SELECT
                    t.keyword,
                    m.product_line,
                    m.content_type,
                    t.total_article_number,
                    t.calendar_week,
                    t.crawl_at_local_time
                FROM market_trend t
                INNER JOIN market_mst m ON m.analysis_type = 'trend' AND t.keyword = m.keyword
                WHERE DATE(t.crawl_at_local_time) = %s
                AND m.product_line = %s
                ORDER BY t.crawl_at_local_time DESC
                LIMIT 500
            """
            cursor.execute(query, (target_date, category))

        rows = cursor.fetchall()

        results['columns'] = columns
        results['total_count'] = len(rows)
        results['data'] = rows

        cursor.close()
        conn.close()

    except Exception as e:
        results['error'] = str(e)

    return JsonResponse(results)


def market_demand_raw_data(request):
    """Market 수요증감율 Raw Data API"""
    date_str = request.GET.get('date')
    category = request.GET.get('category', 'TV')  # TV or HHP

    if date_str:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    else:
        target_date = (datetime.now() - timedelta(days=1)).date()

    results = {
        'date': str(target_date),
        'category': category,
        'columns': [],
        'data': [],
        'total_count': 0
    }

    try:
        conn = get_dx_connection()
        cursor = conn.cursor()

        # openai_forecast_results 테이블 조회
        columns = [
            'product_name', 'event', 'metric_type', 'event_offset',
            'event_value', 'comment', 'week', 'forecast_result', 'crawled_at'
        ]

        query = """
            SELECT
                f.product_name,
                f.event,
                f.metric_type,
                f.event_offset,
                f.event_value,
                f.comment,
                f.week,
                f.forecast_result,
                f.crawled_at
            FROM openai_forecast_results f
            JOIN openai_keywords k ON f.product_name = k.product_name
                AND REPLACE(UPPER(f.event), '_', ' ') = UPPER(k.event_name)
            WHERE f.crawled_at::date = %s
            AND k.category = %s
            ORDER BY f.crawled_at DESC
            LIMIT 500
        """
        cursor.execute(query, (target_date, category))

        rows = cursor.fetchall()

        results['columns'] = columns
        results['total_count'] = len(rows)
        results['data'] = rows

        cursor.close()
        conn.close()

    except Exception as e:
        results['error'] = str(e)

    return JsonResponse(results)


def market_promotion_raw_data(request):
    """Market Promotion Raw Data API"""
    date_str = request.GET.get('date')
    retailer = request.GET.get('retailer', '')

    if date_str:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    else:
        target_date = (datetime.now() - timedelta(days=1)).date()

    # 분석대상일(월요일) 계산
    days_since_monday = target_date.weekday()
    analysis_monday = target_date - timedelta(days=days_since_monday)

    results = {
        'date': str(target_date),
        'analysis_date': str(analysis_monday),
        'retailer': retailer,
        'columns': [],
        'data': [],
        'total_count': 0
    }

    try:
        conn = get_dx_connection()
        cursor = conn.cursor()

        # openai_retailer_promotions 테이블 조회
        columns = [
            'id', 'retailer', 'product', 'sku', 'brand', 'keyword',
            'country', 'promo_type', 'start_date', 'end_date',
            'price_original', 'price_promo', 'discount_rate', 'crawled_at'
        ]

        query = """
            SELECT
                id,
                retailer,
                product,
                sku,
                brand,
                keyword,
                country,
                promo_type,
                start_date,
                end_date,
                price_original,
                price_promo,
                discount_rate,
                crawled_at
            FROM openai_retailer_promotions
            WHERE crawled_at = %s
        """

        params = [analysis_monday.strftime('%Y-%m-%d')]

        if retailer:
            query += " AND retailer = %s"
            params.append(retailer)

        query += " ORDER BY crawled_at DESC, id DESC LIMIT 500"

        cursor.execute(query, params)

        rows = cursor.fetchall()

        # 총 개수 조회 (LIMIT 없이)
        count_query = """
            SELECT COUNT(*)
            FROM openai_retailer_promotions
            WHERE crawled_at = %s
        """
        count_params = [analysis_monday.strftime('%Y-%m-%d')]

        if retailer:
            count_query += " AND retailer = %s"
            count_params.append(retailer)

        cursor.execute(count_query, count_params)
        total_count = cursor.fetchone()[0]

        results['columns'] = columns
        results['total_count'] = total_count
        results['data'] = rows

        cursor.close()
        conn.close()

    except Exception as e:
        results['error'] = str(e)

    return JsonResponse(results)
