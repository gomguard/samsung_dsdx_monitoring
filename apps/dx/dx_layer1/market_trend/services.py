from datetime import timedelta

from apps.common.dx_schedules import get_kst_time_info, get_schedule_kst_info
from apps.dx.dx_layer1.common.context import SECTION_TITLES


def get_layer1_stats(cursor, target_date, now):
    """
    Market Trend Layer1 통계 검증
    - market_mst 기준 기대건수 vs market_trend 수집건수 비교
    - 키워드 커버리지 (등록 vs 수집)
    - TV/HHP 카테고리별 상세 데이터

    Returns: {'check': {...}, 'failed_items': []}
    """
    next_day = target_date + timedelta(days=1)

    # DB에서 Market Trend 스케줄 정보 가져오기 (KST 변환 포함)
    market_trend_info = get_schedule_kst_info('market_trend', target_date, now)

    # market_trend_info가 None인 경우 기본값 사용
    if not market_trend_info:
        kst_start = get_kst_time_info(23, target_date)
        market_trend_info = {
            'us_start_hour': 23,
            'collection_duration_min': 300,
            'kst_start': kst_start,
            'kst_end': {'full_display': f"{next_day} 18:00"},  # 23시 + 5시간 (KST 13시 + 5시간)
            'time_status': None,
            'is_pending': False,
            'is_collecting': False,
            'collection_done': True
        }

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

    # ===== 키워드 커버리지 (등록 키워드 vs 수집 키워드) =====
    # 등록된 키워드 수 (product_line별)
    cursor.execute("""
        SELECT product_line, COUNT(*) as cnt
        FROM market_mst WHERE analysis_type = 'trend'
        GROUP BY product_line
        ORDER BY product_line
    """)
    keyword_registered = {row[0]: row[1] for row in cursor.fetchall()}

    # 수집된 고유 키워드 수 (product_line별)
    cursor.execute("""
        SELECT m.product_line, COUNT(DISTINCT t.keyword) as cnt
        FROM market_trend t
        INNER JOIN market_mst m ON m.analysis_type = 'trend' AND t.keyword = m.keyword
        WHERE DATE(t.crawl_at_local_time) = %s
        GROUP BY m.product_line
    """, (target_date,))
    keyword_collected = {row[0]: row[1] for row in cursor.fetchall()}

    # 누락된 키워드 목록 조회 (product_line별)
    cursor.execute("""
        SELECT m.product_line, m.keyword
        FROM market_mst m
        WHERE m.analysis_type = 'trend'
          AND NOT EXISTS (
              SELECT 1 FROM market_trend t
              WHERE t.keyword = m.keyword
                AND DATE(t.crawl_at_local_time) = %s
          )
        ORDER BY m.product_line, m.keyword
    """, (target_date,))
    missing_keywords_raw = cursor.fetchall()
    missing_keywords_by_pl = {}
    for row in missing_keywords_raw:
        pl = row[0]
        if pl not in missing_keywords_by_pl:
            missing_keywords_by_pl[pl] = []
        missing_keywords_by_pl[pl].append(row[1])

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

    hhp_market_items = []
    hhp_market_total = 0
    hhp_market_expected = 0

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

        # 상태 판정: 100% = OK, 100% 미만 = CRITICAL (스케줄 기반)
        if market_trend_info['is_pending']:
            status = 'PENDING'
        elif expected == 0:
            status = 'PENDING'
        elif rate >= 100:
            status = 'OK'
        elif market_trend_info['is_collecting']:
            status = 'COLLECTING'
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
        else:
            hhp_market_items.append(item_data)
            hhp_market_total += collected
            hhp_market_expected += expected

    # Event, News 순서로 정렬
    tv_market_items.sort(key=lambda x: content_order.get(x['name'], 99))
    hhp_market_items.sort(key=lambda x: content_order.get(x['name'], 99))

    # TV 전체 상태 계산
    if tv_market_expected > 0:
        tv_market_rate = (tv_market_total / tv_market_expected) * 100
    else:
        tv_market_rate = 0 if tv_market_total == 0 else 100

    if market_trend_info['is_pending']:
        tv_market_status = 'PENDING'
    elif tv_market_expected == 0:
        tv_market_status = 'PENDING'
    elif tv_market_rate >= 100:
        tv_market_status = 'OK'
    elif market_trend_info['is_collecting']:
        tv_market_status = 'COLLECTING'
    else:
        tv_market_status = 'CRITICAL'

    # HHP 전체 상태 계산
    if hhp_market_expected > 0:
        hhp_market_rate = (hhp_market_total / hhp_market_expected) * 100
    else:
        hhp_market_rate = 0 if hhp_market_total == 0 else 100

    if market_trend_info['is_pending']:
        hhp_market_status = 'PENDING'
    elif hhp_market_expected == 0:
        hhp_market_status = 'PENDING'
    elif hhp_market_rate >= 100:
        hhp_market_status = 'OK'
    elif market_trend_info['is_collecting']:
        hhp_market_status = 'COLLECTING'
    else:
        hhp_market_status = 'CRITICAL'

    # 키워드 커버리지 데이터 구성 (product_line별)
    tv_kw_registered = keyword_registered.get('TV', 0)
    tv_kw_collected = keyword_collected.get('TV', 0)
    tv_kw_missing = missing_keywords_by_pl.get('TV', [])
    tv_kw_rate = round((tv_kw_collected / tv_kw_registered * 100), 1) if tv_kw_registered > 0 else 100

    hhp_kw_registered = keyword_registered.get('HHP', 0)
    hhp_kw_collected = keyword_collected.get('HHP', 0)
    hhp_kw_missing = missing_keywords_by_pl.get('HHP', [])
    hhp_kw_rate = round((hhp_kw_collected / hhp_kw_registered * 100), 1) if hhp_kw_registered > 0 else 100

    # 전체 키워드 커버리지
    total_kw_registered = tv_kw_registered + hhp_kw_registered
    total_kw_collected = tv_kw_collected + hhp_kw_collected
    total_kw_missing = len(tv_kw_missing) + len(hhp_kw_missing)
    total_kw_rate = round((total_kw_collected / total_kw_registered * 100), 1) if total_kw_registered > 0 else 100

    # 키워드 커버리지 기준 상태 판정 함수
    def get_keyword_coverage_status(registered, collected, is_pending, is_collecting):
        if is_pending:
            return 'PENDING'
        if registered == 0:
            return 'PENDING'
        rate = (collected / registered) * 100
        if rate >= 100:
            return 'OK'
        elif is_collecting:
            return 'COLLECTING'
        else:
            return 'CRITICAL'

    # TV 키워드 상태 (정상여부 판단용)
    tv_kw_status = get_keyword_coverage_status(
        tv_kw_registered, tv_kw_collected,
        market_trend_info['is_pending'], market_trend_info['is_collecting']
    )

    # HHP 키워드 상태 (정상여부 판단용)
    hhp_kw_status = get_keyword_coverage_status(
        hhp_kw_registered, hhp_kw_collected,
        market_trend_info['is_pending'], market_trend_info['is_collecting']
    )

    # 카테고리 데이터 구성 (키워드 커버리지 포함)
    tv_market_data = {
        'name': 'TV',
        'total': tv_market_total,
        'expected': tv_market_expected,
        'rate': round(tv_market_rate, 1),
        'status': tv_kw_status,  # 키워드 기준 상태
        'items': tv_market_items,
        'keyword_coverage': {
            'registered': tv_kw_registered,
            'collected': tv_kw_collected,
            'missing_count': len(tv_kw_missing),
            'missing_keywords': tv_kw_missing[:10],  # 최대 10개만
            'rate': tv_kw_rate,
            'status': tv_kw_status
        }
    }

    hhp_market_data = {
        'name': 'HHP',
        'total': hhp_market_total,
        'expected': hhp_market_expected,
        'rate': round(hhp_market_rate, 1),
        'status': hhp_kw_status,  # 키워드 기준 상태
        'items': hhp_market_items,
        'keyword_coverage': {
            'registered': hhp_kw_registered,
            'collected': hhp_kw_collected,
            'missing_count': len(hhp_kw_missing),
            'missing_keywords': hhp_kw_missing[:10],  # 최대 10개만
            'rate': hhp_kw_rate,
            'status': hhp_kw_status
        }
    }

    # Market Trend 전체 상태 (키워드 커버리지 기준)
    market_overall_status = get_keyword_coverage_status(
        total_kw_registered, total_kw_collected,
        market_trend_info['is_pending'], market_trend_info['is_collecting']
    )

    # 수집량 rate (행 건수 기준)
    if market_total_expected > 0:
        market_overall_rate = (market_total_collected / market_total_expected) * 100
    else:
        market_overall_rate = 0 if market_total_collected == 0 else 100

    market_ok_count = sum(1 for s in [tv_kw_status, hhp_kw_status] if s == 'OK')

    check = {
        'name': SECTION_TITLES['market_trend'],
        'description': f'{market_ok_count}/2 카테고리 정상',
        'actual': market_total_collected,
        'expected': market_total_expected,
        'rate': round(market_overall_rate, 1),
        'status': market_overall_status,
        'check_type': 'market_trend',
        'categories': [tv_market_data, hhp_market_data],
        'us_time': f'{target_date} {market_trend_info["us_start_hour"]:02d}:00',
        'kr_time': market_trend_info['kst_start']['full_display'],
        'kr_time_end': market_trend_info['kst_end']['full_display'],
        'is_dst': market_trend_info['kst_start']['is_dst'],
        # 키워드 커버리지 요약
        'keyword_coverage': {
            'total_registered': total_kw_registered,
            'total_collected': total_kw_collected,
            'total_missing': total_kw_missing,
            'rate': total_kw_rate,
            'status': market_overall_status
        }
    }

    return {'check': check, 'failed_items': []}


def get_market_trend_raw_data(cursor, category, content_type, target_date):
    """
    Market Trend 원본 데이터 조회
    - category: TV 또는 HHP
    - content_type: Event, News 등 (빈 문자열이면 전체)
    - target_date: 조회 날짜 (date 객체)

    Returns: {'category': ..., 'content_type': ..., 'date': ..., 'columns': [...], 'data': [...], 'total_count': int}
    """
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

    return {
        'category': category,
        'content_type': content_type,
        'date': str(target_date),
        'columns': columns,
        'data': rows,
        'total_count': len(rows)
    }
