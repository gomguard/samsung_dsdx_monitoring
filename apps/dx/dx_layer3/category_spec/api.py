"""
Layer 3 카테고리별 특성 API
"""

from django.http import JsonResponse
from datetime import datetime, timedelta
from apps.common.db import get_dx_connection
from apps.common.response import safe_error, log_error
from apps.dx.dx_layer3.dashboard.services import (
    load_category_rules,
    validate_table_name,
    validate_select_query,
    get_status,
    get_category_display_name,
    get_category_description,
    get_non_product_set,
)


def category_spec_detail(request):
    """카테고리별 특성 상세 API - 규칙별 요약 또는 상세 데이터

    Parameters:
        - display_name: 화면 표시 이름 (TV 카테고리 특성, Forecast 등)
        - type: 하위호환용 (tv, hhp)
        - mode: summary면 규칙별 요약, 없으면 상세 데이터
        - rule_id: 특정 규칙의 상세 데이터
    """
    date_str = request.GET.get('date')
    display_name = request.GET.get('display_name', '')
    product_line = request.GET.get('type', '')  # 하위호환
    mode = request.GET.get('mode', '')  # summary: 규칙별 요약
    rule_id = request.GET.get('rule_id', '')  # 특정 규칙 상세

    if date_str:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    else:
        target_date = (datetime.now() - timedelta(days=1)).date()

    try:
        # DB에서 규칙 로드
        rules = load_category_rules()

        # display_name으로 section_code 찾기
        target_category = ''
        if display_name:
            for rule in rules:
                rule_sec = rule.get('section_code', '').lower()
                rule_section_name = rule.get('section_name', '').strip()
                if rule_section_name == display_name:
                    target_category = rule_sec
                    break

        # 하위호환: type 파라미터로 category 결정
        if not target_category and product_line:
            if product_line == 'tv':
                target_category = 'tv_retail'
            elif product_line == 'hhp':
                target_category = 'hhp_retail'
            elif product_line == 'forecast':
                target_category = 'market_forecast'

        conn = get_dx_connection()
        cursor = conn.cursor()

        # mode=summary: 규칙별 요약 반환
        if mode == 'summary':
            rules_summary = []

            for rule in rules:
                rule_section = rule.get('section_code', '').lower()

                # target_category와 매칭되는 규칙만 처리
                if target_category and rule_section != target_category:
                    continue

                rule_id_val = rule.get('rule_id')
                detail_code = rule.get('detail_code')
                detail_name = rule.get('detail_name')
                table_name = rule.get('table_name', '')
                validate_table_name(table_name)
                field1 = rule.get('field1')
                threshold = rule.get('threshold')
                error_message = rule.get('error_message')
                query_template = rule.get('query', '')

                if not query_template:
                    continue

                # date_column (빈값이면 날짜 필터 없음)
                date_col = (rule.get('date_column') or '').strip()
                has_date_filter = bool(date_col)

                try:
                    # 전체 건수 쿼리 (date_column 기반)
                    if has_date_filter:
                        total_query = f"SELECT COUNT(*) FROM {table_name} WHERE DATE({date_col}) = %s"
                        cursor.execute(total_query, (target_date,))
                    else:
                        total_query = f"SELECT COUNT(*) FROM {table_name}"
                        cursor.execute(total_query)

                    total_count = cursor.fetchone()[0] or 0

                    # 이상치 쿼리 실행
                    query = query_template.replace('{table}', table_name).replace('{date_col}', date_col)
                    if not query.strip().upper().startswith('SELECT'):
                        raise ValueError(f'허용되지 않은 쿼리 유형: {detail_code}')
                    # psycopg2 파라미터 바인딩용 이스케이프: LIKE의 %를 %%로
                    query = query.replace('%%', '%')
                    query = query.replace('%', '%%').replace('%%s', '%s')

                    if has_date_filter:
                        cursor.execute(query, (target_date,))
                    else:
                        cursor.execute(query)

                    anomaly_rows = cursor.fetchall()
                    col_names = [desc[0] for desc in cursor.description] if cursor.description else []
                    anomaly_count = len(anomaly_rows)

                    # 비제품 제외 카운트
                    item_idx = col_names.index('item') if 'item' in col_names else -1
                    acct_idx = col_names.index('account_name') if 'account_name' in col_names else -1
                    if anomaly_rows and item_idx >= 0 and acct_idx >= 0:
                        pairs = list({(r[item_idx], r[acct_idx]) for r in anomaly_rows})
                        non_products = get_non_product_set(cursor, table_name, rule.get('product_line'), pairs)
                        if non_products:
                            anomaly_count = sum(1 for r in anomaly_rows if (r[item_idx], r[acct_idx]) not in non_products)

                    rules_summary.append({
                        'rule_id': rule_id_val,
                        'detail_code': detail_code,
                        'detail_name': detail_name,
                        'field1': field1,
                        'threshold': threshold,
                        'error_message': error_message,
                        'total': total_count,
                        'anomaly': anomaly_count,
                        'error_count': anomaly_count
                    })

                except Exception as e:
                    conn.rollback()
                    log_error(e)

            cursor.close()
            conn.close()

            total_checked = sum(r['total'] for r in rules_summary)
            total_anomalies = sum(r['anomaly'] for r in rules_summary)

            return JsonResponse({
                'date': str(target_date),
                'product_line': display_name or target_category.upper(),
                'total_checked': total_checked,
                'total_anomalies': total_anomalies,
                'rule_summary': rules_summary
            })

        # rule_id로 상세 데이터 조회
        category_rules = load_category_rules()
        target_rule = None

        for rule in category_rules:
            if str(rule.get('rule_id', '')) == str(rule_id):
                target_rule = rule
                break

        if not target_rule:
            # 기본 하위호환 (rule_id가 없을 때)
            if product_line == 'tv' and check_type == 'screen_size':
                target_rule = next((r for r in category_rules if r.get('rule_id') == '1'), None)
            elif product_line == 'tv' and check_type == 'price':
                target_rule = next((r for r in category_rules if r.get('rule_id') == '2'), None)
            else:
                target_rule = next((r for r in category_rules if r.get('rule_id') == '3'), None)

        if not target_rule:
            cursor.close()
            conn.close()
            return JsonResponse({'error': '규칙을 찾을 수 없습니다.', 'anomalies': []})

        # 테이블과 날짜 컬럼 설정
        table_name = target_rule.get('table_name', 'tv_retail_com')
        validate_table_name(table_name)
        date_col = (target_rule.get('date_column') or '').strip()
        has_date_filter = bool(date_col)

        # 쿼리 가져와서 실행
        query_template = target_rule.get('query', '')
        if query_template:
            query = query_template.replace('{table}', table_name).replace('{date_col}', date_col)
            if not validate_select_query(query):
                return JsonResponse({'status': 'error', 'message': '허용되지 않은 쿼리 유형'})
            # psycopg2 파라미터 바인딩용 이스케이프: LIKE의 %를 %%로
            query = query.replace('%%', '%')
            query = query.replace('%', '%%').replace('%%s', '%s')

            # date_column이 있으면 날짜 파라미터 전달, 없으면 파라미터 없이 실행
            if has_date_filter:
                cursor.execute(query, (target_date,))
            else:
                cursor.execute(query)
        else:
            cursor.close()
            conn.close()
            return JsonResponse({'error': '쿼리가 정의되지 않았습니다.', 'anomalies': []})

        # 결과를 딕셔너리 리스트로 변환
        columns = [desc[0] for desc in cursor.description]
        anomalies = []
        for row in cursor.fetchall():
            row_dict = dict(zip(columns, row))
            # crawl_datetime을 문자열로 변환
            if 'crawl_datetime' in row_dict and row_dict['crawl_datetime']:
                row_dict['crawl_datetime'] = str(row_dict['crawl_datetime'])
            if 'crawl_strdatetime' in row_dict and row_dict['crawl_strdatetime']:
                row_dict['crawl_strdatetime'] = str(row_dict['crawl_strdatetime'])
            anomalies.append(row_dict)

        # account_name, item, crawl_strdatetime 순 정렬
        anomalies.sort(key=lambda r: (
            r.get('account_name') or '',
            r.get('item') or '',
            r.get('crawl_strdatetime') or r.get('crawl_datetime') or ''
        ))

        # item_mst에서 mst_id, is_product 병합 (retail_com 테이블인 경우)
        if 'retail_com' in table_name and anomalies:
            product_line_val = (target_rule.get('product_line') or '').lower()
            mst_table = validate_table_name('hhp_item_mst' if 'hhp' in product_line_val or 'hhp' in table_name else 'tv_item_mst')
            pairs = list({(r.get('item', ''), r.get('account_name', '')) for r in anomalies})
            if pairs:
                placeholders = ' OR '.join(['(item = %s AND account_name = %s)'] * len(pairs))
                params = [v for p in pairs for v in p]
                cursor.execute(f"SELECT id, item, account_name, is_product, is_checked FROM {mst_table} WHERE {placeholders}", params)
                mst_map = {}
                for row in cursor.fetchall():
                    mst_map[(row[1], row[2])] = {'mst_id': row[0], 'is_product': row[3], 'is_checked': row[4]}
                for a in anomalies:
                    key = (a.get('item', ''), a.get('account_name', ''))
                    mst = mst_map.get(key)
                    if mst:
                        a['mst_id'] = mst['mst_id']
                        a['is_product'] = mst['is_product']
                        a['is_checked'] = mst['is_checked']
                    else:
                        a['mst_id'] = None
                        a['is_product'] = None
                        a['is_checked'] = None

        cursor.close()
        conn.close()

        # check_type 결정
        field1 = target_rule.get('field1', '')
        check_type = 'screen_size' if 'screen' in field1 else 'price'

        # display_columns 파싱 (db컬럼:표시명|db컬럼:표시명 형식)
        display_columns_str = target_rule.get('display_columns') or ''
        display_columns = []
        if display_columns_str:
            for col_pair in display_columns_str.split('|'):
                if ':' in col_pair:
                    db_col, display_name = col_pair.split(':', 1)
                    display_columns.append({'key': db_col.strip(), 'label': display_name.strip()})

        # 리테일러별로 그룹화
        is_master_table = table_name.endswith('_mst')
        retailer_data = {}
        if anomalies:
            for row in anomalies:
                retailer_name = row.get('account_name', 'Unknown')
                if retailer_name not in retailer_data:
                    retailer_data[retailer_name] = []
                retailer_data[retailer_name].append(row)

        return JsonResponse({
            'date': str(target_date),
            'product_line': target_rule.get('product_line', product_line).upper(),
            'check_type': check_type,
            'total_anomalies': len(anomalies),
            'display_columns': display_columns,
            'table_name': table_name,
            'anomalies': anomalies,
            'is_master_table': is_master_table,
            'retailer_data': retailer_data,
            'retailer_counts': {k: len(v) for k, v in retailer_data.items()}
        })

    except Exception as e:
        log_error(e)
        return safe_error(e, anomalies=[])


def category_rules(request):
    """카테고리별 특성 검증 규칙 목록 API (DB 기반)

    Parameters:
        - section: section_code로 필터링 (tv_retail, hhp_retail, market_forecast 등)
        - display_name: 화면 표시 이름으로 필터링 (TV 카테고리 특성, Forecast 등)
    """
    section_param = request.GET.get('section', request.GET.get('category', ''))
    display_name = request.GET.get('display_name', '')

    try:
        rules = load_category_rules()

        # display_name으로 필터링 (section별 그룹 조회)
        if display_name:
            display_to_section = {}
            for rule in rules:
                rule_sec = rule.get('section_code', '').lower()
                rule_section_name = rule.get('section_name', '').strip()
                if rule_section_name and rule_section_name not in display_to_section:
                    display_to_section[rule_section_name] = rule_sec

            target_section = display_to_section.get(display_name, '')
            if target_section:
                section_param = target_section

        # section별 필터링
        filtered_rules = []
        for rule in rules:
            rule_section = rule.get('section_code', '').lower()

            if not section_param or section_param == 'all' or rule_section == section_param:
                filtered_rules.append({
                    'rule_id': rule.get('rule_id'),
                    'detail_code': rule.get('detail_code'),
                    'detail_name': rule.get('detail_name'),
                    'section_code': rule.get('section_code'),
                    'product_line': rule.get('product_line'),
                    'field1': rule.get('field1'),
                    'threshold': rule.get('threshold'),
                    'error_message': rule.get('error_message'),
                    'retailer': rule.get('retailer')
                })

        return JsonResponse({
            'status': 'success',
            'section': section_param or 'all',
            'total_rules': len(filtered_rules),
            'rules': filtered_rules
        })

    except Exception as e:
        log_error(e)
        return JsonResponse({'status': 'error', 'message': '처리 중 오류가 발생했습니다.'})
