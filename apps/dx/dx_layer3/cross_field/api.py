"""
Layer 3 크로스 필드 검증 API
"""

from django.http import JsonResponse
from datetime import datetime, timedelta
from apps.common.db import get_dx_connection
from apps.common.retail_columns import get_editable_columns
from apps.common.response import safe_error, log_error
from apps.dx.dx_layer3.dashboard.services import (
    validate_crossfield,
    validate_review_detail_match,
    get_crossfield_normal_counts,
    get_all_no_review_texts,
    load_crossfield_rules,
)


def cross_field_detail(request):
    """크로스 필드 논리 검증 상세 API (DB 기반) - 검증 유형별 요약"""
    date_str = request.GET.get('date')
    product_line = request.GET.get('type', 'tv')
    rule_id = request.GET.get('rule_id')  # 특정 규칙 상세 조회 시
    days = int(request.GET.get('days', 1))
    if days < 1:
        days = 1
    if days > 30:
        days = 30

    if date_str:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    else:
        target_date = (datetime.now() - timedelta(days=1)).date()

    # product_line을 section으로 변환
    section_map = {'tv': 'tv_retail', 'hhp': 'hhp_retail'}
    section = section_map.get(product_line, f'{product_line}_retail')

    try:
        # 검증은 항상 target_date 하루만 실행
        crossfield_result = validate_crossfield(target_date, section)

        # 특정 규칙 상세 조회
        if rule_id:
            for rule_result in crossfield_result['rule_results']:
                if str(rule_result['rule_id']) == str(rule_id):
                    table_name = crossfield_result.get('table_name', '')
                    date_col = crossfield_result.get('date_col', '')
                    validation_type = rule_result.get('validation_type', '')

                    # 1일치: 기존 로직 (검증 결과 그대로 반환)
                    if days == 1:
                        anomalies = []
                        for detail in rule_result['error_details']:
                            anomaly = {
                                'item': detail.get('item'),
                                'account_name': detail.get('account_name'),
                                'page_type': detail.get('page_type'),
                            }
                            for key, value in detail.items():
                                if key not in ['item', 'account_name', 'page_type']:
                                    anomaly[key] = value
                            if validation_type == 'cross_detail_mismatch':
                                validation_info = validate_review_detail_match(detail, product_line, return_detail=True)
                                anomaly['validation_tag'] = validation_info.get('reason', '')
                                anomaly['expected_pattern'] = validation_info.get('expected_pattern', '')
                            anomalies.append(anomaly)
                    else:
                        # N일치: 에러 아이템의 원본 데이터를 N일간 조회
                        # 에러 아이템 추출 (account_name + item 쌍)
                        error_pairs = set()
                        for detail in rule_result['error_details']:
                            acct = detail.get('account_name', '')
                            item = detail.get('item', '')
                            if acct and item:
                                error_pairs.add((acct, item))

                        if not error_pairs or not table_name or not date_col:
                            anomalies = []
                        else:
                            # select_fields에서 기본 표시 컬럼 결정
                            select_fields_raw = rule_result.get('select_fields', '')
                            if select_fields_raw:
                                dynamic_cols = [f.strip() for f in select_fields_raw.split('|') if f.strip()]
                            else:
                                # error_details의 키에서 추출
                                exclude = {'id', 'item', 'account_name', 'page_type', date_col, 'product_url'}
                                dynamic_cols = []
                                if rule_result['error_details']:
                                    for k in rule_result['error_details'][0].keys():
                                        if k not in exclude:
                                            dynamic_cols.append(k)

                            # 리테일러별 아이템 그룹핑
                            retailer_items = {}
                            for acct, item in error_pairs:
                                retailer_items.setdefault(acct, []).append(item)

                            conn_days = get_dx_connection()
                            cur_days = conn_days.cursor()
                            anomalies = []

                            from_date = target_date - timedelta(days=days - 1)
                            from apps.common.retail_columns import get_retailer_columns
                            for acct, items in retailer_items.items():
                                # 리테일러 전체 수집 컬럼으로 SELECT
                                retail_cols = get_retailer_columns(product_line, acct)
                                fixed_cols = ['id', 'account_name', 'item', 'page_type', date_col]
                                # 기본 표시 컬럼 먼저, 나머지 수집 컬럼 추가
                                added = set(fixed_cols + ['product_url'])
                                ordered_cols = list(fixed_cols)
                                for c in dynamic_cols:
                                    if c not in added:
                                        ordered_cols.append(c)
                                        added.add(c)
                                for c in retail_cols:
                                    if c not in added:
                                        ordered_cols.append(c)
                                        added.add(c)
                                ordered_cols.append('product_url')
                                select_sql = ', '.join(ordered_cols)

                                placeholders = ', '.join(['%s'] * len(items))
                                cur_days.execute(f"""
                                    SELECT {select_sql}
                                    FROM {table_name}
                                    WHERE account_name = %s
                                      AND item IN ({placeholders})
                                      AND DATE({date_col}::timestamp) >= %s
                                      AND DATE({date_col}::timestamp) <= %s
                                    ORDER BY item, {date_col}
                                """, [acct] + items + [str(from_date), str(target_date)])
                                cols_desc = [desc[0] for desc in cur_days.description]
                                for row in cur_days.fetchall():
                                    anomaly = {}
                                    for i, col_name in enumerate(cols_desc):
                                        val = row[i]
                                        anomaly[col_name] = str(val) if val is not None else None
                                    anomalies.append(anomaly)

                            cur_days.close()
                            conn_days.close()

                    # account_name, item, crawl_datetime 순으로 정렬
                    anomalies.sort(key=lambda x: (
                        x.get('account_name', '') or '',
                        x.get('item', '') or '',
                        str(x.get('crawl_datetime', '') or x.get('crawl_strdatetime', '') or '')
                    ))

                    # editable 컬럼 수집 (리테일러별 합집합)
                    editable_columns = []
                    if table_name in ('tv_retail_com', 'hhp_retail_com'):
                        seen_retailers = set()
                        all_editable = set()
                        for a in anomalies:
                            r = a.get('account_name', '')
                            if r and r not in seen_retailers:
                                seen_retailers.add(r)
                                cols = get_editable_columns(product_line, r)
                                all_editable.update(cols)
                        editable_columns = sorted(all_editable)

                    # 기존 정상 처리 이력 조회
                    normal_reviews = {}
                    conn_nr = get_dx_connection()
                    cur_nr = conn_nr.cursor()
                    cur_nr.execute("""
                        SELECT record_id, column_name, memo, reason, created_id, created_at
                        FROM monitoring_corrections
                        WHERE layer = 3 AND correction_type = 'cross_field'
                          AND crawl_date = %s AND status = 'normal'
                          AND table_name = %s AND rule_id = %s
                    """, (str(target_date), table_name, rule_id))
                    for nr_row in cur_nr.fetchall():
                        nr_key = f"{nr_row[0]}_{nr_row[1]}"
                        normal_reviews[nr_key] = {
                            'memo': nr_row[2] or '',
                            'reason': nr_row[3] or '',
                            'created_id': nr_row[4] or '',
                            'created_at': str(nr_row[5]) if nr_row[5] else ''
                        }
                    cur_nr.close()
                    conn_nr.close()

                    # 정상 처리된 record_id 집합
                    normal_record_ids = set()
                    for nr_key in normal_reviews:
                        rid = nr_key.split('_')[0]
                        normal_record_ids.add(rid)

                    # 리테일러별 집계 (건수 계산의 단일 기준)
                    retailer_summary = {}
                    for a in anomalies:
                        retailer = a.get('account_name', 'Unknown')
                        if retailer not in retailer_summary:
                            retailer_summary[retailer] = {'count': 0, 'items': []}
                        if str(a.get('id', '')) not in normal_record_ids:
                            retailer_summary[retailer]['count'] += 1
                        item = a.get('item', '')
                        if item and item not in retailer_summary[retailer]['items']:
                            retailer_summary[retailer]['items'].append(item)

                    adjusted_total = sum(r['count'] for r in retailer_summary.values())

                    # 리테일러별 전체 수집 컬럼 (컬럼 선택용)
                    from apps.common.retail_columns import get_retailer_columns
                    retailer_columns = {}
                    for r in retailer_summary:
                        cols = get_retailer_columns(product_line, r)
                        retailer_columns[r] = cols

                    return JsonResponse({
                        'date': str(target_date),
                        'days': days,
                        'product_line': product_line.upper(),
                        'rule_id': rule_result['rule_id'],
                        'detail_code': rule_result['detail_code'],
                        'field1': rule_result['field1'],
                        'field2': rule_result.get('field2'),
                        'validation_type': validation_type,
                        'error_message': rule_result['error_message'],
                        'total_anomalies': adjusted_total,
                        'retailer_summary': retailer_summary,
                        'anomalies': anomalies,
                        'select_fields': rule_result.get('select_fields', ''),
                        'table_name': table_name,
                        'editable_columns': editable_columns,
                        'normal_reviews': normal_reviews,
                        'retailer_columns': retailer_columns,
                    })

            return JsonResponse({'error': '해당 규칙을 찾을 수 없습니다.'})

        # 규칙별 요약 반환 (검증 유형별 건수) - 0건도 포함
        # 정상 처리 건수 차감
        table_name_for_normal = 'tv_retail_com' if product_line == 'tv' else 'hhp_retail_com'
        normal_counts = get_crossfield_normal_counts(target_date, table_name_for_normal)

        rule_summary = []
        total_anomalies = 0
        for r in crossfield_result['rule_results']:
            adjusted_count = max(0, r['error_count'] - normal_counts.get(r['rule_id'], 0))
            rule_summary.append({
                'rule_id': r['rule_id'],
                'detail_code': r['detail_code'],
                'field1': r['field1'],
                'field2': r.get('field2'),
                'validation_type': r.get('validation_type', ''),
                'error_message': r['error_message'],
                'error_count': adjusted_count,
                'query': r.get('query', ''),
                'select_fields': r.get('select_fields', '')
            })
            total_anomalies += adjusted_count

        # 테이블/컬럼 정보 (플레이스홀더 치환용)
        table_name = crossfield_result.get('table_name', '')
        date_col = crossfield_result.get('date_col', '')

        return JsonResponse({
            'date': str(target_date),
            'product_line': product_line.upper(),
            'total_anomalies': total_anomalies,
            'rule_summary': rule_summary,
            'table_name': table_name,
            'date_col': date_col,
            'no_review_texts': get_all_no_review_texts()
        })

    except Exception as e:
        log_error(e)
        return safe_error(e)


def sentiment_cross_detail(request):
    """Sentiment ↔ 리뷰 일관성 상세 API"""
    date_str = request.GET.get('date')
    product_line = request.GET.get('type', 'tv')

    if date_str:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    else:
        target_date = (datetime.now() - timedelta(days=1)).date()

    try:
        conn = get_dx_connection()
        cursor = conn.cursor()

        anomalies = []

        if product_line == 'tv':
            # TV: sentiment 점수가 실제로 있는데 리뷰 수가 0인 경우 (None/none 문자열 제외)
            cursor.execute("""
                SELECT
                    r.id,
                    r.item,
                    r.account_name,
                    r.page_type,
                    r.count_of_star_ratings,
                    s.sentiment_score,
                    r.main_rank,
                    r.crawl_datetime
                FROM tv_retail_sentiment s
                JOIN tv_retail_com r ON s.retail_com_id = r.id
                WHERE DATE(r.crawl_datetime::timestamp) = %s
                AND s.sentiment_score IS NOT NULL
                AND LOWER(s.sentiment_score::text) NOT IN ('none', 'null', '')
                AND (
                    r.count_of_star_ratings IS NULL
                    OR r.count_of_star_ratings = ''
                    OR r.count_of_star_ratings = '0'
                    OR r.count_of_star_ratings = 'No reviews'
                    OR r.count_of_star_ratings = 'No ratings'
                )
                ORDER BY r.crawl_datetime DESC
                LIMIT 100
            """, (target_date,))

            rows = cursor.fetchall()
            for row in rows:
                anomalies.append({
                    'retail_com_id': row[0],
                    'item': row[1],
                    'account_name': row[2],
                    'page_type': row[3],
                    'errors': [{
                        'field': 'sentiment ↔ count_of_star_ratings',
                        'error': f'리뷰 수가 "{row[4]}"인데 sentiment 점수({row[5]})가 존재'
                    }]
                })
        else:
            # HHP: sentiment 점수가 실제로 있는데 리뷰 수가 0인 경우 (None/none 문자열 제외)
            # crawl_strdatetime을 timestamp로 캐스팅하여 날짜 비교
            cursor.execute("""
                SELECT
                    r.id,
                    r.item,
                    r.account_name,
                    r.page_type,
                    r.count_of_star_ratings,
                    s.sentiment_score,
                    r.main_rank,
                    r.crawl_strdatetime
                FROM hhp_retail_sentiment s
                JOIN hhp_retail_com r ON s.retail_com_id = r.id
                WHERE DATE(r.crawl_strdatetime::timestamp) = %s
                AND s.sentiment_score IS NOT NULL
                AND LOWER(s.sentiment_score::text) NOT IN ('none', 'null', '')
                AND (
                    r.count_of_star_ratings IS NULL
                    OR r.count_of_star_ratings = ''
                    OR r.count_of_star_ratings = '0'
                    OR r.count_of_star_ratings = 'No reviews'
                    OR r.count_of_star_ratings = 'No ratings'
                )
                ORDER BY r.crawl_strdatetime DESC
                LIMIT 100
            """, (target_date,))

            rows = cursor.fetchall()
            for row in rows:
                anomalies.append({
                    'retail_com_id': row[0],
                    'item': row[1],
                    'account_name': row[2],
                    'page_type': row[3],
                    'errors': [{
                        'field': 'sentiment ↔ count_of_star_ratings',
                        'error': f'리뷰 수가 "{row[4]}"인데 sentiment 점수({row[5]})가 존재'
                    }]
                })

        cursor.close()
        conn.close()

        return JsonResponse({
            'date': str(target_date),
            'product_line': product_line.upper(),
            'total_anomalies': len(anomalies),
            'anomalies': anomalies
        })

    except Exception as e:
        log_error(e)
        return safe_error(e, anomalies=[])


def comp_product_cross_detail(request):
    """Comp Product 자사/경쟁사 구분 상세 API"""
    date_str = request.GET.get('date')

    if date_str:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    else:
        target_date = (datetime.now() - timedelta(days=1)).date()

    # 월 범위 계산
    month_start = target_date.replace(day=1).strftime('%Y-%m-%d')
    if target_date.month == 12:
        month_end_date = target_date.replace(year=target_date.year + 1, month=1, day=1) - timedelta(days=1)
    else:
        month_end_date = target_date.replace(month=target_date.month + 1, day=1) - timedelta(days=1)
    month_end = month_end_date.strftime('%Y-%m-%d')

    try:
        conn = get_dx_connection()
        cursor = conn.cursor()

        anomalies = []

        # 해당 월에 실행된 comp_product 배치 조회
        cursor.execute("""
            SELECT batch_id, MAX(created_at) as last_run
            FROM market_comp_product
            WHERE batch_id IS NOT NULL
              AND created_at >= %s AND created_at < %s::date + INTERVAL '1 day'
            GROUP BY batch_id
            ORDER BY last_run DESC
            LIMIT 1
        """, (month_start, month_end))
        batch_row = cursor.fetchone()
        batch_id = batch_row[0] if batch_row else None

        if batch_id:
            # samsung_series_name에 comp_brand가 포함된 경우
            cursor.execute("""
                SELECT
                    samsung_series_name,
                    comp_brand,
                    comp_product_name,
                    created_at
                FROM market_comp_product
                WHERE batch_id = %s
                AND LOWER(samsung_series_name) LIKE '%%' || LOWER(comp_brand) || '%%'
                ORDER BY created_at DESC
                LIMIT 100
            """, (batch_id,))

            rows = cursor.fetchall()
            for idx, row in enumerate(rows):
                anomalies.append({
                    'item': str(idx + 1),
                    'account_name': row[1],  # comp_brand
                    'page_type': row[0],  # samsung_series_name
                    'errors': [{
                        'field': 'samsung_series_name ↔ comp_brand',
                        'error': f'삼성 시리즈({row[0]})에 경쟁사 브랜드({row[1]})가 포함됨'
                    }]
                })

        cursor.close()
        conn.close()

        return JsonResponse({
            'date': str(target_date),
            'batch_id': batch_id,
            'total_anomalies': len(anomalies),
            'anomalies': anomalies
        })

    except Exception as e:
        log_error(e)
        return safe_error(e, anomalies=[])


def crossfield_rules(request):
    """크로스필드 검증 규칙 목록 API (DB 기반)"""
    section = request.GET.get('section', request.GET.get('category', request.GET.get('type', 'all')))

    # 이전 호환성: tv → tv_retail, hhp → hhp_retail
    section_map = {'tv': 'tv_retail', 'hhp': 'hhp_retail'}
    section = section_map.get(section, section)

    try:
        rules = load_crossfield_rules()

        # section별 필터링
        filtered_rules = []
        for rule in rules:
            rule_section = rule.get('section_code', '').lower()

            # all이면 전체, 아니면 해당 section만 포함
            if section == 'all' or rule_section == section:
                filtered_rules.append({
                    'rule_id': rule.get('rule_id'),
                    'detail_code': rule.get('detail_code'),
                    'detail_name': rule.get('detail_name'),
                    'section_code': rule.get('section_code'),
                    'field1': rule.get('field1'),
                    'field2': rule.get('field2'),
                    'error_message': rule.get('error_message'),
                    'retailer': rule.get('retailer'),
                    'validation_type': rule.get('validation_type')
                })

        return JsonResponse({
            'status': 'success',
            'section': section,
            'total_rules': len(filtered_rules),
            'rules': filtered_rules
        })

    except Exception as e:
        log_error(e)
        return JsonResponse({'status': 'error', 'message': '처리 중 오류가 발생했습니다.'})
