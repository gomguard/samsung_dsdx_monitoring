from datetime import timedelta
from decimal import Decimal

from apps.common.dx_schedules import get_kst_time_info, get_schedule_kst_info
from apps.dx.dx_layer1.common.context import SECTION_TITLES


def get_layer1_stats(cursor, target_date, now):
    """
    Market 수요증감율 대시보드 통계.
    Returns {'check': {...}, 'failed_items': []}
    """
    next_day = target_date + timedelta(days=1)

    # DB에서 Market Demand 스케줄 정보 가져오기 (KST 변환 포함)
    market_demand_info = get_schedule_kst_info('market_demand', target_date, now)

    # market_demand_info가 None인 경우 기본값 사용
    if not market_demand_info:
        kst_start = get_kst_time_info(18, target_date)
        market_demand_info = {
            'us_start_hour': 18,
            'collection_duration_min': 300,
            'kst_start': kst_start,
            'kst_end': {'full_display': f"{next_day} 04:00"},
            'time_status': None,
            'is_pending': False,
            'is_collecting': False,
            'collection_done': True
        }

    demand_is_pending = market_demand_info['is_pending']
    demand_collection_done = market_demand_info['collection_done']

    def get_demand_stats(query_date):
        """수요증감율 통계 조회 (특정 날짜 기준)"""
        nine_weeks_later = query_date + timedelta(weeks=9)
        one_week_later = query_date + timedelta(weeks=1)

        # 9주 이내 키워드 수 (카테고리별) - 오늘 제외 (수집 스크립트와 동일)
        cursor.execute("""
            SELECT k.category, COUNT(*) as cnt
            FROM openai_keywords k
            JOIN openai_event_mst e ON k.event_name = e.event_name
            WHERE e.is_active = true
            AND e.event_date > %s AND e.event_date <= %s
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
        target = target_demand.get(category, 0)  # 1주 이내 제외 없이 전체 대상
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
        demand_description = '대기중'
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

    check = {
        'name': SECTION_TITLES['market_demand'],
        'description': demand_description,
        'status': demand_overall_status,
        'check_type': 'market_demand',
        'date': target_date.strftime('%Y-%m-%d'),
        'categories': demand_categories,
        'expected': demand_total_target,
        'total_target': demand_total_target,
        'actual': demand_total_collected,
        'total_collected': demand_total_collected,
        'rate': demand_rate,
        'us_time': f'{target_date} {market_demand_info["us_start_hour"]:02d}:00',
        'kr_time': market_demand_info['kst_start']['full_display'],
        'kr_time_end': market_demand_info['kst_end']['full_display'],
        'is_dst': market_demand_info['kst_start']['is_dst']
    }

    return {'check': check, 'failed_items': []}


def get_market_demand_raw_data(cursor, category, target_date):
    """
    Market 수요증감율 Raw Data 조회.
    Returns data dict with columns, data, total_count.
    """
    results = {
        'date': str(target_date),
        'category': category,
        'columns': [],
        'data': [],
        'total_count': 0
    }

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

    # Decimal -> float 변환 (trailing zero 제거: 4.70 -> 4.7)
    processed = []
    for row in rows:
        processed.append(tuple(
            float(v) if isinstance(v, Decimal) else v
            for v in row
        ))

    results['columns'] = columns
    results['total_count'] = len(rows)
    results['data'] = processed

    return results


def get_missing_keywords(cursor, category, target_date):
    """
    Market 수요증감율 부족 키워드 상세 조회 (openai_keywords 기준).
    Returns data dict with missing_keywords, total_missing, summary.
    """
    results = {
        'date': str(target_date),
        'category': category,
        'missing_keywords': [],
        'total_missing': 0,
        'summary': {}
    }

    nine_weeks_later = target_date + timedelta(weeks=9)

    # 대상 키워드 조회 (9주 이내 이벤트) - 수집 스크립트와 동일 (오늘 제외)
    target_query = """
        SELECT k.category, k.product_name, k.event_name, e.event_date
        FROM openai_keywords k
        JOIN openai_event_mst e ON k.event_name = e.event_name
        WHERE e.is_active = true
        AND e.event_date > %s AND e.event_date <= %s
        {category_filter}
        ORDER BY k.category, e.event_date, k.product_name
    """

    if category != 'all':
        target_query = target_query.format(category_filter=f"AND k.category = '{category}'")
    else:
        target_query = target_query.format(category_filter="")

    cursor.execute(target_query, (target_date.strftime('%Y-%m-%d'), nine_weeks_later.strftime('%Y-%m-%d')))
    target_keywords = cursor.fetchall()

    # 수집된 키워드 조회 (openai_forecast_results)
    collected_query = """
        SELECT DISTINCT k.category, f.product_name,
               REPLACE(UPPER(f.event), '_', ' ') as event_name
        FROM openai_forecast_results f
        JOIN openai_keywords k ON f.product_name = k.product_name
            AND REPLACE(UPPER(f.event), '_', ' ') = UPPER(k.event_name)
        WHERE f.crawled_at::date = %s
        {category_filter}
    """

    if category != 'all':
        collected_query = collected_query.format(category_filter=f"AND k.category = '{category}'")
    else:
        collected_query = collected_query.format(category_filter="")

    cursor.execute(collected_query, (target_date.strftime('%Y-%m-%d'),))
    collected_set = set()
    for row in cursor.fetchall():
        collected_set.add((row[0], row[1], row[2].upper()))

    # 부족한 키워드 찾기
    missing_keywords = []
    summary_by_category = {}

    for row in target_keywords:
        cat, product_name, event_name, event_date = row
        key = (cat, product_name, event_name.upper())

        # 전체 대상 카운트
        if cat not in summary_by_category:
            summary_by_category[cat] = {'total': 0, 'missing': 0}
        summary_by_category[cat]['total'] += 1

        if key not in collected_set:
            missing_keywords.append({
                'category': cat,
                'product_name': product_name,
                'event_name': event_name,
                'event_date': str(event_date)
            })
            summary_by_category[cat]['missing'] += 1

    results['missing_keywords'] = missing_keywords
    results['total_missing'] = len(missing_keywords)
    results['summary'] = summary_by_category

    return results
