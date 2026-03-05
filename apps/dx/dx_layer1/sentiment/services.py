from datetime import datetime, timedelta
from apps.common.response import log_error
from apps.dx.dx_layer1.common.context import SECTION_TITLES
from apps.common.dx_schedules import get_kst_time_info, get_schedule_kst_info

RETAILERS = ['amazon', 'bestbuy', 'walmart']

# SQL Injection 방지용 화이트리스트
ALLOWED_TABLES = {
    'tv_retail_sentiment', 'hhp_retail_sentiment',
    'tv_retail_com', 'hhp_retail_com',
}
ALLOWED_CRAWL_COLS = {'crawl_datetime', 'crawl_strdatetime'}


def _determine_status(rate, target, sentiment_info):
    """공통 상태 판단 로직 (스케줄 기반)"""
    if sentiment_info['is_pending']:
        return 'PENDING'
    elif target == 0:
        return 'PENDING'
    elif rate >= 100:
        return 'OK'
    elif sentiment_info['is_collecting']:
        return 'ANALYZING'
    elif rate >= 90:
        return 'WARNING'
    else:
        return 'CRITICAL'


def _build_category_stats(cursor, category, target_date, next_day, sentiment_info, sentiment_pending):
    """
    카테고리별(TV/HHP) Sentiment 통계 생성
    dashboard/api.py의 TV/HHP Sentiment 검증 로직 공통화
    """
    # 테이블/컬럼 매핑
    if category == 'TV':
        sentiment_table = 'tv_retail_sentiment'
        com_table = 'tv_retail_com'
        crawl_col = 'crawl_datetime'
    else:
        sentiment_table = 'hhp_retail_sentiment'
        com_table = 'hhp_retail_com'
        crawl_col = 'crawl_strdatetime'

    # 화이트리스트 검증
    if sentiment_table not in ALLOWED_TABLES or com_table not in ALLOWED_TABLES:
        raise ValueError(f"허용되지 않은 테이블: {sentiment_table}, {com_table}")
    if crawl_col not in ALLOWED_CRAWL_COLS:
        raise ValueError(f"허용되지 않은 컬럼: {crawl_col}")

    start_time = f'{target_date} 00:00:00'
    end_time = f'{next_day} 00:00:00'

    # 분석 대상 (로그 테이블에서 스냅샷 조회)
    cursor.execute("""
        SELECT COALESCE(SUM(target_count), 0)
        FROM retail_sentiment_analysis_log
        WHERE category = %s AND analysis_date = %s
    """, (category, target_date))
    total_target = cursor.fetchone()[0] or 0

    # 분석 완료 (실제 sentiment 테이블에서 조회)
    cursor.execute(f"""
        SELECT COUNT(*)
        FROM {sentiment_table} s
        JOIN {com_table} r ON s.retail_com_id = r.id
        WHERE r.{crawl_col}::timestamp >= %s AND r.{crawl_col}::timestamp < %s
    """, (start_time, end_time))
    total_analyzed = cursor.fetchone()[0] or 0

    # 리테일러별/시간대별 대상 (로그 테이블에서 조회)
    cursor.execute("""
        SELECT retailer, period, target_count
        FROM retail_sentiment_analysis_log
        WHERE category = %s AND analysis_date = %s
    """, (category, target_date))
    target_details = {f"{row[0]}_{row[1]}": row[2] for row in cursor.fetchall()}

    # 리테일러별/시간대별 분석완료 (실제 테이블에서 조회)
    cursor.execute(f"""
        SELECT
            LOWER(r.account_name),
            CASE WHEN EXTRACT(HOUR FROM r.{crawl_col}::timestamp) < 12 THEN '오전' ELSE '오후' END as period,
            COUNT(*) as analyzed_count
        FROM {sentiment_table} s
        JOIN {com_table} r ON s.retail_com_id = r.id
        WHERE r.{crawl_col}::timestamp >= %s AND r.{crawl_col}::timestamp < %s
        GROUP BY LOWER(r.account_name), period
        ORDER BY LOWER(r.account_name), period
    """, (start_time, end_time))
    analyzed_details = {f"{row[0]}_{row[1]}": row[2] for row in cursor.fetchall()}

    # Sentiment 시간대 정의 - DB 기반 US→KST 자동 변환 (서머타임 고려)
    sentiment_time_slots_info = [
        {
            'period': '오전',
            'us_time': f'{next_day} {sentiment_info["us_start_hour"]:02d}:00',
            'kr_time': sentiment_info['kst_start']['full_display'],
            'kr_time_end': sentiment_info['kst_end']['full_display'],
            'is_dst': sentiment_info['kst_start']['is_dst']
        },
        {
            'period': '오후',
            'us_time': f'{next_day} {sentiment_info["us_start_hour"]:02d}:00',
            'kr_time': sentiment_info['kst_start']['full_display'],
            'kr_time_end': sentiment_info['kst_end']['full_display'],
            'is_dst': sentiment_info['kst_start']['is_dst']
        },
    ]

    # 시간대별 데이터
    time_slots = []
    ok_slots = 0
    active_slots = 0

    for slot_info in sentiment_time_slots_info:
        period = slot_info['period']
        slot_target = 0
        slot_analyzed = 0
        retailers_data = []

        for retailer in RETAILERS:
            key = f"{retailer}_{period}"
            target = target_details.get(key, 0)
            analyzed = analyzed_details.get(key, 0)
            rate = round((analyzed / target * 100), 1) if target > 0 else 0

            status = _determine_status(rate, target, sentiment_info)

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
        slot_status = _determine_status(slot_rate, slot_target, sentiment_info)

        if slot_target > 0 and not sentiment_pending:
            active_slots += 1
            if slot_status == 'OK':
                ok_slots += 1

        time_slots.append({
            'time': period,
            'us_time': slot_info['us_time'],
            'kr_time': slot_info['kr_time'],
            'kr_time_end': slot_info['kr_time_end'],
            'is_dst': slot_info['is_dst'],
            'target': slot_target,
            'analyzed': slot_analyzed,
            'rate': slot_rate,
            'status': slot_status,
            'retailers': retailers_data
        })

    total_rate = round((total_analyzed / total_target * 100), 1) if total_target > 0 else 0
    total_status = _determine_status(total_rate, total_target, sentiment_info)

    return {
        'name': category,
        'target': total_target,
        'analyzed': total_analyzed,
        'rate': total_rate,
        'status': total_status,
        'time_slots': time_slots
    }


def get_layer1_stats(cursor, target_date, now):
    """
    대시보드용 Sentiment 검증 통계
    dashboard/api.py L410-786에서 추출

    Returns: {'check': {...}, 'failed_items': []}
    """
    next_day = target_date + timedelta(days=1)

    # DB에서 Sentiment 스케줄 정보 가져오기 (KST 변환 포함)
    # Sentiment는 target_date 데이터를 target_date 다음날(next_day)에 분석하므로 next_day 기준으로 조회
    sentiment_info = get_schedule_kst_info('sentiment', next_day, now)

    # sentiment_info가 None인 경우 기본값 사용
    if not sentiment_info:
        kst_start = get_kst_time_info(1, next_day)
        # KST 종료 시간 계산 (시작 + 240분)
        kr_start_hour = kst_start['hour']
        kr_start_date = kst_start['date']
        kr_end_dt = datetime(kr_start_date.year, kr_start_date.month, kr_start_date.day, kr_start_hour, 0, 0) + timedelta(minutes=240)
        sentiment_info = {
            'us_start_hour': 1,
            'collection_duration_min': 240,
            'kst_start': kst_start,
            'kst_end': {'full_display': kr_end_dt.strftime('%Y-%m-%d %H:00')},
            'time_status': None,
            'is_pending': False,
            'is_collecting': False,
            'collection_done': True
        }

    # Sentiment 상태 판정 (스케줄 기반 - next_day 기준으로 계산됨)
    sentiment_pending = sentiment_info['is_pending'] or sentiment_info['is_collecting']

    # TV Sentiment 데이터
    tv_sentiment_data = _build_category_stats(cursor, 'TV', target_date, next_day, sentiment_info, sentiment_pending)

    # HHP Sentiment 데이터
    hhp_sentiment_data = _build_category_stats(cursor, 'HHP', target_date, next_day, sentiment_info, sentiment_pending)

    # Sentiment 통합 (TV + HHP)
    total_sentiment_target = tv_sentiment_data['target'] + hhp_sentiment_data['target']
    total_sentiment_analyzed = tv_sentiment_data['analyzed'] + hhp_sentiment_data['analyzed']
    total_sentiment_rate = round((total_sentiment_analyzed / total_sentiment_target * 100), 1) if total_sentiment_target > 0 else 0

    # 통합 상태 결정: 스케줄 기반 (둘 중 더 나쁜 상태)
    status_priority = {'OK': 0, 'WARNING': 1, 'ANALYZING': 2, 'CRITICAL': 3, 'PENDING': 4}
    if total_sentiment_target == 0:
        total_sentiment_status = 'PENDING'
    elif sentiment_info['is_pending']:
        total_sentiment_status = 'PENDING'
    elif total_sentiment_rate >= 100:
        # 100%면 시간에 관계없이 결과 표시
        total_sentiment_status = 'OK'
    elif sentiment_info['is_collecting']:
        total_sentiment_status = 'ANALYZING'
    else:
        tv_priority = status_priority.get(tv_sentiment_data['status'], 0)
        hhp_priority = status_priority.get(hhp_sentiment_data['status'], 0)
        if tv_priority >= hhp_priority:
            total_sentiment_status = tv_sentiment_data['status']
        else:
            total_sentiment_status = hhp_sentiment_data['status']

    # 정상 카테고리 수 계산
    sentiment_ok_count = sum(1 for s in [tv_sentiment_data['status'], hhp_sentiment_data['status']] if s == 'OK')

    check = {
        'name': SECTION_TITLES['sentiment'],
        'description': f'{sentiment_ok_count}/2 카테고리 정상',
        'actual': total_sentiment_analyzed,
        'target': total_sentiment_target,
        'rate': total_sentiment_rate,
        'status': total_sentiment_status,
        'check_type': 'sentiment',
        'us_time': f'{next_day} {sentiment_info["us_start_hour"]:02d}:00',
        'kr_time': sentiment_info['kst_start']['full_display'],
        'kr_time_end': sentiment_info['kst_end']['full_display'],
        'is_dst': sentiment_info['kst_start']['is_dst'],
        'categories': [tv_sentiment_data, hhp_sentiment_data]
    }

    return {
        'check': check,
        'failed_items': []
    }


def get_sentiment_stats(cursor, target_date):
    """
    감성 분석 통계 - 분석 대상 vs 저장된 결과
    sentiment/api.py sentiment_stats()에서 추출

    Returns: dict (tv, hhp 카테고리별 통계)
    """
    next_day = target_date + timedelta(days=1)
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

    return results


def get_sentiment_raw_data(cursor, category, retailer, period, target_date):
    """
    감성분석 원본 데이터 조회
    sentiment/api.py sentiment_raw_data()에서 추출

    Returns: dict (columns, data, total_count 등)
    """
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

    columns = [
        'id', 'retail_com_id', 'item', 'sentiment_score',
        'final_interpretation', 'created_at', 'batch_id'
    ]

    if category == 'TV':
        # TV 감성분석 데이터 조회
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

    return results
