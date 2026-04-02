from datetime import datetime, timedelta

from apps.common.dx_schedules import get_schedule_kst_info
from apps.dx.dx_layer1.common.context import SECTION_TITLES
from apps.dx.dx_layer1.common.quarter_utils import get_quarter_info, get_competitor_batch


def get_layer1_stats(cursor, target_date, now):
    """
    Market Competitor 대시보드 검증 통계.
    Returns {'check': {...}, 'failed_items': [], 'comp_batch_id': ...}
    """
    target_month = target_date.month
    target_year = target_date.year

    # 스케줄 시간 정보
    comp_schedule_info = get_schedule_kst_info('market_competitor', target_date, now)

    # 분기 정보
    q_info = get_quarter_info(target_date)
    quarter_start = q_info['quarter_start']
    quarter_end = q_info['quarter_end']
    quarter_name = q_info['quarter_name']

    # 배치 조회
    comp_batch_id, comp_last_run = get_competitor_batch(cursor, quarter_start, quarter_end)

    # 분기 첫날인지 확인 (조회 날짜 기준)
    is_quarter_first = (target_date.day == 1 and target_date.month in [1, 4, 7, 10])

    # 다음 분기 첫날 계산
    if target_month <= 3:
        next_quarter_start = f"{target_year}-04-01"
    elif target_month <= 6:
        next_quarter_start = f"{target_year}-07-01"
    elif target_month <= 9:
        next_quarter_start = f"{target_year}-10-01"
    else:
        next_quarter_start = f"{target_year + 1}-01-01"

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

    # ===== 키워드 커버리지 (삼성 시리즈 × 경쟁사 브랜드 조합) =====
    # 등록된 삼성 키워드 목록 (product_line별)
    cursor.execute("""
        SELECT product_line, keyword
        FROM market_mst
        WHERE analysis_type = 'competitor' AND content_type = 'samsung' AND is_active = true
        ORDER BY product_line, keyword
    """)
    comp_samsung_keywords = {}
    for row in cursor.fetchall():
        pl = row[0]
        if pl not in comp_samsung_keywords:
            comp_samsung_keywords[pl] = []
        comp_samsung_keywords[pl].append(row[1])

    # 등록된 경쟁사 브랜드 목록 (product_line별)
    cursor.execute("""
        SELECT product_line, keyword
        FROM market_mst
        WHERE analysis_type = 'competitor' AND content_type = 'comp' AND is_active = true
        ORDER BY product_line, keyword
    """)
    comp_brand_keywords = {}
    for row in cursor.fetchall():
        pl = row[0]
        if pl not in comp_brand_keywords:
            comp_brand_keywords[pl] = []
        comp_brand_keywords[pl].append(row[1])

    # 수집된 삼성 시리즈 × 경쟁사 브랜드 조합 (product_line별)
    comp_collected_combinations = {}
    if comp_batch_id:
        cursor.execute("""
            SELECT
                category,
                samsung_series_name,
                comp_brand
            FROM market_comp_product
            WHERE batch_id = %s
            GROUP BY category, samsung_series_name, comp_brand
        """, (comp_batch_id,))
        for row in cursor.fetchall():
            pl = row[0]
            if pl not in comp_collected_combinations:
                comp_collected_combinations[pl] = set()
            comp_collected_combinations[pl].add((row[1], row[2]))

    # 키워드 커버리지 계산 (product_line별)
    comp_keyword_coverage = {}
    for pl in ['TV', 'HHP']:
        samsung_kws = set(comp_samsung_keywords.get(pl, []))
        comp_kws = set(comp_brand_keywords.get(pl, []))
        collected_combos = comp_collected_combinations.get(pl, set())

        # 수집된 삼성 시리즈와 경쟁사 브랜드 추출
        collected_samsung = set(combo[0] for combo in collected_combos)
        collected_comp = set(combo[1] for combo in collected_combos)

        # 누락된 삼성 키워드
        missing_samsung = samsung_kws - collected_samsung
        # 누락된 경쟁사 브랜드
        missing_comp = comp_kws - collected_comp

        # 전체 기대 조합 수 vs 수집된 조합 수
        expected_combos = len(samsung_kws) * len(comp_kws)
        collected_combo_count = len(collected_combos)

        combo_rate = round((collected_combo_count / expected_combos * 100), 1) if expected_combos > 0 else 100

        comp_keyword_coverage[pl] = {
            'samsung_registered': len(samsung_kws),
            'samsung_collected': len(collected_samsung),
            'samsung_missing': list(missing_samsung)[:10],
            'comp_registered': len(comp_kws),
            'comp_collected': len(collected_comp),
            'comp_missing': list(missing_comp)[:10],
            'combo_expected': expected_combos,
            'combo_collected': collected_combo_count,
            'combo_rate': combo_rate,
            'total_missing': len(missing_samsung) + len(missing_comp)
        }

    # Market Competitor 카테고리별 상세 데이터
    comp_categories = []
    comp_total_collected = 0
    comp_total_expected = 0
    comp_statuses = []
    failed_items = []

    for category in ['TV', 'HHP']:
        collected = comp_collected.get(category, 0)
        expected = comp_expected.get(category, 0)
        kw_cov = comp_keyword_coverage.get(category, {})

        # 수집률 계산
        if expected > 0:
            rate = (collected / expected) * 100
        else:
            rate = 0 if collected == 0 else 100

        # 키워드 커버리지율 (조합 기준)
        combo_rate = kw_cov.get('combo_rate', 100)

        # 상태 판정 - 키워드 커버리지 기준
        if not is_quarter_first:
            status = 'PENDING'
        elif expected == 0:
            status = 'PENDING'
        elif combo_rate >= 100:
            status = 'OK'
        elif combo_rate >= 90:
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
            'status': status,
            'keyword_coverage': kw_cov
        })

        if status in ('WARNING', 'CRITICAL'):
            error_type = '커버리지 미달' if status == 'CRITICAL' else '주의'
            failed_items.append({
                'source': f"Market Competitor - {category}",
                'error_type': error_type,
                'expected': expected,
                'actual': collected,
                'timestamp': f"커버리지 {combo_rate}%",
                'status': status,
                'combo_rate': combo_rate
            })

    # 전체 키워드 커버리지 계산
    total_combo_expected = sum(kw.get('combo_expected', 0) for kw in comp_keyword_coverage.values())
    total_combo_collected = sum(kw.get('combo_collected', 0) for kw in comp_keyword_coverage.values())
    total_combo_rate = round((total_combo_collected / total_combo_expected * 100), 1) if total_combo_expected > 0 else 100
    total_kw_missing = sum(kw.get('total_missing', 0) for kw in comp_keyword_coverage.values())

    # Market Competitor 전체 상태 (키워드 커버리지 기준)
    if not is_quarter_first:
        comp_overall_status = 'PENDING'
    elif total_combo_expected == 0:
        comp_overall_status = 'PENDING'
    elif total_combo_rate >= 100:
        comp_overall_status = 'OK'
    elif total_combo_rate >= 90:
        comp_overall_status = 'WARNING'
    else:
        comp_overall_status = 'CRITICAL'

    # 수집량 rate (행 건수 기준)
    if comp_total_expected > 0:
        comp_overall_rate = (comp_total_collected / comp_total_expected) * 100
    else:
        comp_overall_rate = 0 if comp_total_collected == 0 else 100

    comp_ok_count = len([s for s in comp_statuses if s == 'OK'])

    if not is_quarter_first:
        comp_description = '분석대상일 아님'
    else:
        comp_description = f'{comp_ok_count}/{len(comp_statuses)} 카테고리 정상'

    check = {
        'name': SECTION_TITLES['market_competitor'],
        'description': comp_description,
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
            'end': quarter_end,
            'next_start': next_quarter_start
        },
        'is_target_date': is_quarter_first,
        'us_time': f'{target_date} {comp_schedule_info["us_start_hour"]:02d}:00' if comp_schedule_info else '',
        'kr_time': comp_schedule_info['kst_start']['full_display'] if comp_schedule_info else '',
        'is_dst': comp_schedule_info['kst_start']['is_dst'] if comp_schedule_info else False,
        'keyword_coverage': {
            'total_combo_expected': total_combo_expected,
            'total_combo_collected': total_combo_collected,
            'total_combo_rate': total_combo_rate,
            'total_missing': total_kw_missing
        }
    }

    return {
        'check': check,
        'failed_items': failed_items,
        'comp_batch_id': comp_batch_id,
    }


def get_competitor_keywords(cursor, category):
    """
    Market Competitor 키워드 등록 현황 — market_mst 테이블.
    Returns data dict with columns, data, total_count.
    """
    columns = ['id', 'product_line', 'content_type', 'keyword', 'is_active', 'created_at']

    query = """
        SELECT id, product_line, content_type, keyword, is_active, created_at
        FROM market_mst
        WHERE analysis_type = 'competitor'
    """
    params = []

    if category:
        query += " AND product_line = %s"
        params.append(category)

    query += " ORDER BY product_line, content_type, keyword"

    cursor.execute(query, params)
    rows = cursor.fetchall()

    data = []
    for row in rows:
        row_list = list(row)
        for i, val in enumerate(row_list):
            if isinstance(val, datetime):
                row_list[i] = val.strftime('%Y-%m-%d %H:%M:%S')
        data.append(row_list)

    return {
        'category': category,
        'columns': columns,
        'data': data,
        'total_count': len(data),
    }


def get_competitor_raw_data(cursor, category, target_date):
    """
    Market Competitor Raw Data — market_comp_product 테이블.
    Returns data dict with columns, data, total_count, batch_id.
    """
    # 분기 계산
    q_info = get_quarter_info(target_date)
    quarter_start = q_info['quarter_start']
    quarter_end = q_info['quarter_end']

    empty_columns = [
        'category', 'samsung_series_name', 'comp_brand', 'comp_series_name',
        'expected_release', 'release_status', 'comment', 'calender_week', 'created_at'
    ]

    results = {
        'date': str(target_date),
        'category': category,
        'columns': [],
        'data': [],
        'total_count': 0,
    }

    # 해당 분기 최신 배치 조회
    comp_batch_id, _ = get_competitor_batch(cursor, quarter_start, quarter_end)

    if not comp_batch_id:
        results['columns'] = empty_columns
        return results

    results['batch_id'] = comp_batch_id

    columns = [
        'id', 'category', 'samsung_series_name', 'comp_brand', 'comp_series_name',
        'expected_release', 'release_status', 'comment', 'calender_week', 'created_at'
    ]

    query = """
        SELECT id, category, samsung_series_name, comp_brand, comp_series_name,
               expected_release, release_status, comment, calender_week, created_at
        FROM market_comp_product
        WHERE batch_id = %s
    """
    params = [comp_batch_id]

    if category:
        query += " AND category = %s"
        params.append(category)

    query += " ORDER BY category, samsung_series_name, comp_brand"

    cursor.execute(query, params)
    rows = cursor.fetchall()

    # datetime → str 변환
    data = []
    for row in rows:
        row_list = list(row)
        for i, val in enumerate(row_list):
            if isinstance(val, datetime):
                row_list[i] = val.strftime('%Y-%m-%d %H:%M:%S')
        data.append(row_list)

    results['columns'] = columns
    results['data'] = data
    results['total_count'] = len(data)

    return results


def get_missing_keywords(cursor, category, target_date):
    """
    Market Competitor 부족 키워드(누락된 Samsung Series x Comp Brand 조합) 상세 조회
    """
    from apps.dx.dx_layer1.common.quarter_utils import get_quarter_info, get_competitor_batch
    q_info = get_quarter_info(target_date)
    comp_batch_id, _ = get_competitor_batch(cursor, q_info['quarter_start'], q_info['quarter_end'])

    results = {
        'date': str(target_date),
        'category': category,
        'missing_keywords': [],
        'summary': {}
    }

    cats = ['TV', 'HHP'] if category == 'all' else [category]

    for cat in cats:
        # 삼성 및 경쟁사 키워드
        cursor.execute("SELECT keyword FROM market_mst WHERE analysis_type = 'competitor' AND content_type = 'samsung' AND is_active = true AND product_line = %s", (cat,))
        samsung_kws = [r[0] for r in cursor.fetchall()]

        cursor.execute("SELECT keyword FROM market_mst WHERE analysis_type = 'competitor' AND content_type = 'comp' AND is_active = true AND product_line = %s", (cat,))
        comp_kws = [r[0] for r in cursor.fetchall()]

        expected_combos = set()
        for s_kw in samsung_kws:
            for c_kw in comp_kws:
                expected_combos.add((s_kw, c_kw))

        collected_combos = set()
        if comp_batch_id:
            cursor.execute("""
                SELECT samsung_series_name, comp_brand
                FROM market_comp_product
                WHERE batch_id = %s AND category = %s
                GROUP BY samsung_series_name, comp_brand
            """, (comp_batch_id, cat))
            for row in cursor.fetchall():
                collected_combos.add((row[0], row[1]))

        missing_combos = expected_combos - collected_combos

        for m_s, m_c in missing_combos:
            results['missing_keywords'].append({
                'category': cat,
                'samsung_series': m_s,
                'comp_brand': m_c
            })

        results['summary'][cat] = {
            'total': len(expected_combos),
            'missing': len(missing_combos)
        }

    return results
