from datetime import datetime, timedelta

from apps.dx.dx_layer1.common.context import SECTION_TITLES
from apps.dx.dx_layer1.common.quarter_utils import get_quarter_info, get_competitor_batch


def get_layer1_stats(cursor, target_date, now, comp_batch_id=None):
    """
    Market Competitor Event 대시보드 검증 통계.
    comp_batch_id가 None이면 quarter_utils로 직접 조회.
    Returns {'check': {...}, 'failed_items': []}
    """
    # comp_batch_id가 없으면 분기 정보로 조회
    q_info = get_quarter_info(target_date)
    quarter_start = q_info['quarter_start']
    quarter_end = q_info['quarter_end']

    if comp_batch_id is None:
        comp_batch_id, _ = get_competitor_batch(cursor, quarter_start, quarter_end)

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

    # 다음 달 첫번째 월요일 계산
    if target_date.month == 12:
        next_month_first_day = target_date.replace(year=target_date.year + 1, month=1, day=1)
    else:
        next_month_first_day = target_date.replace(month=target_date.month + 1, day=1)
    next_days_until_monday = (7 - next_month_first_day.weekday()) % 7
    if next_month_first_day.weekday() == 0:  # 이미 월요일이면
        next_first_monday = next_month_first_day
    else:
        next_first_monday = next_month_first_day + timedelta(days=next_days_until_monday)

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
    event_expected_combos = {}  # 키워드 커버리지용 기대 조합
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

        # 기대 조합 목록 (키워드 커버리지용)
        cursor.execute("""
            SELECT
                category,
                comp_brand || '||' || comp_series_name as combo
            FROM market_comp_product
            WHERE batch_id = %s
              AND comp_series_name != 'info_not_available'
            GROUP BY category, comp_brand, comp_series_name
        """, (comp_batch_id,))
        for row in cursor.fetchall():
            cat = row[0]
            if cat not in event_expected_combos:
                event_expected_combos[cat] = set()
            event_expected_combos[cat].add(row[1])

    # 수집된 조합 (키워드 커버리지용)
    # market_comp_event 테이블에서는 comp_sku_name 컬럼 사용
    event_collected_combos = {}
    if event_batch_id:
        cursor.execute("""
            SELECT
                category,
                comp_brand || '||' || comp_sku_name as combo
            FROM market_comp_event
            WHERE batch_id = %s
            GROUP BY category, comp_brand, comp_sku_name
        """, (event_batch_id,))
        for row in cursor.fetchall():
            cat = row[0]
            if cat not in event_collected_combos:
                event_collected_combos[cat] = set()
            event_collected_combos[cat].add(row[1])

    # 키워드 커버리지 계산 (카테고리별)
    event_keyword_coverage = {}
    for pl in ['TV', 'HHP']:
        expected_combos = event_expected_combos.get(pl, set())
        collected_combos = event_collected_combos.get(pl, set())
        missing_combos = expected_combos - collected_combos

        combo_rate = round((len(collected_combos) / len(expected_combos) * 100), 1) if len(expected_combos) > 0 else 100

        event_keyword_coverage[pl] = {
            'combo_expected': len(expected_combos),
            'combo_collected': len(collected_combos),
            'combo_missing': len(missing_combos),
            'combo_rate': combo_rate,
            'missing_samples': list(missing_combos)[:5]  # 샘플 5개만
        }

    # Market Competitor Event 카테고리별 상세 데이터
    event_categories = []
    event_total_collected = 0
    event_total_expected = 0
    event_statuses = []
    failed_items = []

    for category in ['TV', 'HHP']:
        collected = event_collected.get(category, 0)
        expected = event_expected.get(category, 0)
        kw_cov = event_keyword_coverage.get(category, {})

        # 수집률 계산
        if expected > 0:
            rate = (collected / expected) * 100
        else:
            rate = 0 if collected == 0 else 100

        # 키워드 커버리지율 (조합 기준)
        combo_rate = kw_cov.get('combo_rate', 100)

        # 상태 판정 - 키워드 커버리지 기준
        if not is_first_monday:
            status = 'PENDING'
        elif expected == 0:
            status = 'PENDING'
        elif combo_rate >= 100:
            status = 'OK'
        elif combo_rate >= 90:
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
            'status': status,
            'keyword_coverage': kw_cov
        })

        if status in ('WARNING', 'CRITICAL'):
            failed_items.append({
                'category': category,
                'collected': collected,
                'expected': expected,
                'rate': round(rate, 1),
                'status': status,
                'combo_rate': combo_rate
            })

    # 전체 키워드 커버리지 계산
    total_event_combo_expected = sum(kw.get('combo_expected', 0) for kw in event_keyword_coverage.values())
    total_event_combo_collected = sum(kw.get('combo_collected', 0) for kw in event_keyword_coverage.values())
    total_event_combo_rate = round((total_event_combo_collected / total_event_combo_expected * 100), 1) if total_event_combo_expected > 0 else 100
    total_event_combo_missing = sum(kw.get('combo_missing', 0) for kw in event_keyword_coverage.values())

    # Market Competitor Event 전체 상태 (키워드 커버리지 기준)
    if not is_first_monday:
        event_overall_status = 'PENDING'
    elif total_event_combo_expected == 0:
        event_overall_status = 'PENDING'
    elif total_event_combo_rate >= 100:
        event_overall_status = 'OK'
    elif total_event_combo_rate >= 90:
        event_overall_status = 'WARNING'
    else:
        event_overall_status = 'CRITICAL'

    # 수집량 rate (행 건수 기준)
    if event_total_expected > 0:
        event_overall_rate = (event_total_collected / event_total_expected) * 100
    else:
        event_overall_rate = 0 if event_total_collected == 0 else 100

    event_ok_count = len([s for s in event_statuses if s == 'OK'])

    if not is_first_monday:
        event_description = '분석대상일 아님'
    else:
        event_description = f'{event_ok_count}/{len(event_statuses)} 카테고리 정상'

    check = {
        'name': SECTION_TITLES['market_competitor_event'],
        'description': event_description,
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
            'first_monday': first_monday.strftime('%Y-%m-%d'),
            'next_first_monday': next_first_monday.strftime('%Y-%m-%d')
        },
        'is_target_date': is_first_monday,
        'keyword_coverage': {
            'total_combo_expected': total_event_combo_expected,
            'total_combo_collected': total_event_combo_collected,
            'total_combo_rate': total_event_combo_rate,
            'total_missing': total_event_combo_missing
        }
    }

    return {
        'check': check,
        'failed_items': failed_items,
    }


def get_competitor_event_raw_data(cursor, category, target_date):
    """
    Market Competitor Event Raw Data — market_comp_event 테이블.
    Returns data dict with columns, data, total_count, batch_id.
    """
    # 월 범위 계산
    month_start = target_date.replace(day=1)
    if target_date.month == 12:
        month_end = target_date.replace(year=target_date.year + 1, month=1, day=1) - timedelta(days=1)
    else:
        month_end = target_date.replace(month=target_date.month + 1, day=1) - timedelta(days=1)

    empty_columns = [
        'category', 'comp_brand', 'comp_sku_name', 'comp_launch_date',
        'comp_preorder', 'comp_pre_order_start_date', 'comp_preorder_end_date',
        'rumor_release_window', 'rumor_preorder_window', 'rumor_confidence_level',
        'calender_week', 'created_at'
    ]

    results = {
        'date': str(target_date),
        'category': category,
        'columns': [],
        'data': [],
        'total_count': 0,
    }

    # 해당 월 최신 배치 조회
    cursor.execute("""
        SELECT batch_id FROM market_comp_event
        WHERE batch_id IS NOT NULL
          AND created_at >= %s AND created_at < %s::date + INTERVAL '1 day'
        GROUP BY batch_id
        ORDER BY MAX(created_at) DESC
        LIMIT 1
    """, (str(month_start), str(month_end)))
    batch_row = cursor.fetchone()

    if not batch_row:
        results['columns'] = empty_columns
        return results

    batch_id = batch_row[0]
    results['batch_id'] = batch_id

    columns = [
        'id', 'category', 'comp_brand', 'comp_sku_name', 'comp_launch_date',
        'comp_preorder', 'comp_pre_order_start_date', 'comp_preorder_end_date',
        'rumor_release_window', 'rumor_preorder_window', 'rumor_confidence_level',
        'calender_week', 'created_at'
    ]

    query = """
        SELECT id, category, comp_brand, comp_sku_name, comp_launch_date,
               comp_preorder, comp_pre_order_start_date, comp_preorder_end_date,
               rumor_release_window, rumor_preorder_window, rumor_confidence_level,
               calender_week, created_at
        FROM market_comp_event
        WHERE batch_id = %s
    """
    params = [batch_id]

    if category:
        query += " AND category = %s"
        params.append(category)

    query += " ORDER BY category, comp_brand, comp_sku_name"

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
