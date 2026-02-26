"""
Layer 3 API: 이상치/특수 케이스 검수 (Outlier Detection & Special Cases)
- 시계열 이상치 탐지 (전일 대비 급격한 변화)
- 크로스 필드 논리 검증 (Layer 2에서 이동)
- 카테고리별 특성 기반 검증
- 텍스트 이상치 탐지
"""

import os
import csv
from django.http import JsonResponse
from django.conf import settings
from datetime import datetime, timedelta
from apps.common.db import get_dx_connection
from apps.common.response import safe_error, log_error


import re

_DANGEROUS_SQL = {'DROP', 'DELETE', 'TRUNCATE', 'UPDATE', 'INSERT', 'ALTER', 'GRANT', 'REVOKE'}

# 허용 테이블 화이트리스트
_ALLOWED_TABLES = {
    'tv_retail_com', 'hhp_retail_com',
    'tv_item_mst', 'hhp_item_mst',
    'tv_sentiment_com', 'hhp_sentiment_com',
    'comp_product',
    'openai_forecast_results',
}

# exclude_condition 허용 패턴 (개별 조건 단위)
# ex) "field LIKE 'value%'", "field = 'value'", "field IS NULL"
_EXCLUDE_PATTERN = re.compile(
    r"""^\s*\w+\s+(?:
        LIKE\s+'[^']*'          |
        NOT\s+LIKE\s+'[^']*'    |
        =\s*'[^']*'             |
        !=\s*'[^']*'            |
        <>\s*'[^']*'            |
        IS\s+NULL               |
        IS\s+NOT\s+NULL         |
        IN\s*\([^)]+\)
    )\s*$""",
    re.IGNORECASE | re.VERBOSE
)


def _validate_table_name(table_name):
    """테이블명 화이트리스트 검증"""
    if table_name not in _ALLOWED_TABLES:
        raise ValueError(f"허용되지 않은 테이블: {table_name}")
    return table_name


def _validate_select_query(query):
    """SELECT 전용 쿼리인지 검증. 위험 키워드 포함 시 False 반환."""
    upper = query.strip().upper()
    if not upper.startswith('SELECT') and not upper.startswith('WITH'):
        return False
    for keyword in _DANGEROUS_SQL:
        # 단어 경계 체크 (UPDATED 같은 컬럼명 오탐 방지)
        if re.search(r'\b' + keyword + r'\b', upper):
            return False
    if ';' in query:
        return False
    return True


def _validate_exclude_condition(condition):
    """exclude_condition SQL 조각 검증 — 화이트리스트 패턴만 허용"""
    if not condition or not condition.strip():
        return False
    # 세미콜론/주석 차단
    if ';' in condition or '--' in condition or '/*' in condition:
        return False
    # OR로 분리된 각 조건을 개별 검증
    parts = re.split(r'\bOR\b', condition, flags=re.IGNORECASE)
    for part in parts:
        if not _EXCLUDE_PATTERN.match(part.strip()):
            return False
    return True


# ============================================================
# DB 기반 검증 규칙 로드 (monitoring_validation_rules)
# ============================================================
def load_timeseries_rules():
    """DB에서 시계열 이상치 검증 규칙 로드 (monitoring_validation_rules 테이블)"""
    rules = []
    try:
        conn = get_dx_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, detail_code, detail_name, section_code, section_name,
                   table_name, date_column, product_line,
                   check_column, check_type, comparison_type,
                   threshold_pct, threshold_min,
                   error_message, query, sort_order
            FROM monitoring_validation_rules
            WHERE rule_type = 'timeseries' AND is_active = true
            ORDER BY sort_order, id
        """)
        columns = [
            'rule_id', 'detail_code', 'detail_name', 'section_code', 'section_name',
            'table_name', 'date_column', 'product_line',
            'check_column', 'check_type', 'comparison_type',
            'threshold_pct', 'threshold_min',
            'error_message', 'query', 'sort_order'
        ]
        for row in cursor.fetchall():
            rules.append(dict(zip(columns, row)))
        cursor.close()
        conn.close()
    except Exception as e:
        log_error(e)

    return rules



def load_crossfield_rules():
    """DB에서 크로스필드 검증 규칙 로드 (monitoring_validation_rules 테이블)"""
    rules = []
    try:
        conn = get_dx_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, detail_code, detail_name, section_code, section_name,
                   table_name, date_column, product_line, retailer,
                   field1, field2, validation_type,
                   error_message, select_fields, query, sort_order
            FROM monitoring_validation_rules
            WHERE rule_type = 'crossfield' AND is_active = true
            ORDER BY sort_order, id
        """)
        columns = [
            'rule_id', 'detail_code', 'detail_name', 'section_code', 'section_name',
            'table_name', 'date_column', 'product_line', 'retailer',
            'field1', 'field2', 'validation_type',
            'error_message', 'select_fields', 'query', 'sort_order'
        ]
        for row in cursor.fetchall():
            rules.append(dict(zip(columns, row)))
        cursor.close()
        conn.close()
    except Exception as e:
        log_error(e)

    return rules


def load_category_rules():
    """DB에서 카테고리별 특성 검증 규칙 로드 (monitoring_validation_rules 테이블)"""
    rules = []
    try:
        conn = get_dx_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, detail_code, detail_name, section_code, section_name,
                   table_name, date_column, product_line, retailer,
                   field1, validation_type, threshold,
                   error_message, display_columns, query, sort_order
            FROM monitoring_validation_rules
            WHERE rule_type = 'category_spec' AND is_active = true
            ORDER BY sort_order, id
        """)
        columns = [
            'rule_id', 'detail_code', 'detail_name', 'section_code', 'section_name',
            'table_name', 'date_column', 'product_line', 'retailer',
            'field1', 'validation_type', 'threshold',
            'error_message', 'display_columns', 'query', 'sort_order'
        ]
        for row in cursor.fetchall():
            rules.append(dict(zip(columns, row)))
        cursor.close()
        conn.close()
    except Exception as e:
        log_error(e)

    return rules


def _get_non_product_set(cursor, table_name, product_line, pairs):
    """item_mst에서 is_product=false 또는 is_checked=true인 (item, account_name) 집합 반환"""
    if not pairs or 'retail_com' not in table_name:
        return set()
    pl = (product_line or '').lower()
    mst = _validate_table_name('hhp_item_mst' if 'hhp' in pl or 'hhp' in table_name else 'tv_item_mst')
    ph = ' OR '.join(['(item = %s AND account_name = %s)'] * len(pairs))
    params = [v for p in pairs for v in p]
    cursor.execute(f"SELECT item, account_name FROM {mst} WHERE (is_product = false OR is_checked = true) AND ({ph})", params)
    return {(r[0], r[1]) for r in cursor.fetchall()}


def get_no_review_texts(account_name):
    """리테일러별 리뷰없음 텍스트 반환"""
    if account_name == 'Amazon':
        return "'No customer reviews'"
    elif account_name == 'Bestbuy':
        return "'Not yet reviewed'"
    else:  # Walmart
        return "'No ratings yet'"


def get_all_no_review_texts():
    """모든 리테일러의 리뷰없음 텍스트 반환"""
    return "'No customer reviews', 'Not yet reviewed', 'No ratings yet'"


def validate_review_detail_match(row, product_line, return_detail=False):
    """count_of_reviews와 detailed_review_content 매칭 검증 (후처리)

    Args:
        row: dict - 쿼리 결과 행 (count_of_reviews, detailed_review_content, account_name 포함)
        product_line: str - 'tv' 또는 'hhp'
        return_detail: bool - True면 상세 정보(dict) 반환, False면 bool만 반환

    Returns:
        return_detail=False: bool - True면 불일치(에러), False면 정상
        return_detail=True: dict - {
            'is_error': bool,
            'reason': str,
            'expected_pattern': str,
            'pattern_found': bool,
            'max_review_num': int
        }

    패턴 규칙:
        - 전체 공통: review{N} - (예: review1 -, review2 -, ..., review20 -)
    """
    count_of_reviews = row.get('count_of_reviews', '')
    detailed_review_content = row.get('detailed_review_content', '')
    account_name = row.get('account_name', '')

    def make_result(is_error, reason='', pattern='', found=False, max_num=0):
        if return_detail:
            return {
                'is_error': is_error,
                'reason': reason,
                'expected_pattern': pattern,
                'pattern_found': found,
                'max_review_num': max_num
            }
        return is_error

    # count_of_reviews 파싱
    try:
        review_count = int(str(count_of_reviews).replace(',', ''))
    except (ValueError, TypeError):
        return make_result(False, '리뷰 수 파싱 불가')

    if review_count <= 0:
        return make_result(False, '리뷰 수 0 이하')

    # detailed_review_content가 없으면 에러
    if not detailed_review_content or detailed_review_content.strip() == '':
        return make_result(True, '본문 없음', '', False, min(review_count, 20))

    # no_review_texts 체크
    no_review_texts = ['No customer reviews', 'Not yet reviewed', 'No ratings yet']
    if detailed_review_content in no_review_texts:
        return make_result(True, '리뷰없음 텍스트', '', False, min(review_count, 20))

    # 검증할 리뷰 번호 (최대 20까지만)
    max_review_num = min(review_count, 20)

    # 패턴 생성 (전체 공통)
    pattern = f"review{max_review_num} -"

    # 패턴이 detailed_review_content에 있는지 확인
    pattern_found = pattern.lower() in detailed_review_content.lower()

    if pattern_found:
        return make_result(False, '정상', pattern, True, max_review_num)
    else:
        return make_result(True, f'패턴 "{pattern}" 없음', pattern, False, max_review_num)


def get_category_display_name(section_code, rules=None):
    """section_code를 화면에 표시할 이름으로 변환"""
    # rules가 전달되면 첫 번째 규칙의 section_name 사용
    if rules:
        for rule in rules:
            category_name = rule.get('section_name', '').strip()
            if category_name:
                return category_name
    # fallback: section_code 그대로 반환
    return section_code


def get_category_description(category, rules):
    """category의 규칙들을 요약한 description 생성"""
    if not rules:
        return ''
    field_names = list(set(r.get('field1', '') for r in rules if r.get('field1')))
    return ', '.join(field_names) + ' 범위 검증' if field_names else '범위 검증'


def validate_all_category_specs(target_date):
    """카테고리별 특성 검증 - 모든 섹션을 동적으로 처리

    Returns:
        list: 각 섹션별로 그룹화된 검증 결과
        [
            {
                'section_code': 'tv_retail',
                'section_name': 'TV 카테고리 특성',
                'description': 'screen_size, final_sku_price 범위 검증',
                'total': 5000,
                'anomaly': 59,
                'rules': [...]
            },
            ...
        ]
    """
    rules = load_category_rules()
    if not rules:
        return []

    # section별로 규칙 그룹화
    section_rules_map = {}
    for rule in rules:
        sec = rule.get('section_code', '').lower()
        if sec not in section_rules_map:
            section_rules_map[sec] = []
        section_rules_map[sec].append(rule)

    results = []
    conn = get_dx_connection()
    cursor = conn.cursor()

    for section, sec_rules in section_rules_map.items():
        cat_total = 0
        cat_anomaly = 0
        rule_results = []

        for rule in sec_rules:
            rule_id = rule.get('rule_id')
            detail_code = rule.get('detail_code')
            detail_name = rule.get('detail_name')
            table_name = rule.get('table_name', '')
            field1 = rule.get('field1')
            error_message = rule.get('error_message')
            query_template = rule.get('query', '')

            if not query_template:
                continue

            date_col = (rule.get('date_column') or '').strip()
            has_date_filter = bool(date_col)

            try:
                _validate_table_name(table_name)
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
                if not _validate_select_query(query):
                    raise ValueError(f'허용되지 않은 쿼리 유형: {detail_code}')
                # psycopg2 파라미터 바인딩용 이스케이프: LIKE의 %를 %%로
                # 먼저 %%를 %로 통일한 뒤, 다시 %를 %%로 이스케이프 (%s 파라미터는 복원)
                query = query.replace('%%', '%')
                query = query.replace('%', '%%').replace('%%s', '%s')

                # date_column이 있으면 날짜 파라미터 전달, 없으면 파라미터 없이 실행
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
                    non_products = _get_non_product_set(cursor, table_name, rule.get('product_line'), pairs)
                    if non_products:
                        anomaly_count = sum(1 for r in anomaly_rows if (r[item_idx], r[acct_idx]) not in non_products)

                cat_total += total_count
                cat_anomaly += anomaly_count

                rule_results.append({
                    'rule_id': rule_id,
                    'detail_code': detail_code,
                    'detail_name': detail_name,
                    'field1': field1,
                    'error_message': error_message,
                    'total': total_count,
                    'anomaly': anomaly_count
                })

            except Exception as e:
                conn.rollback()
                log_error(e)

        # 섹션별 결과 추가
        results.append({
            'section_code': section,
            'section_name': get_category_display_name(section, sec_rules),
            'description': get_category_description(section, sec_rules),
            'total': cat_total,
            'anomaly': cat_anomaly,
            'rules': rule_results
        })

    cursor.close()
    conn.close()

    return results


def execute_crossfield_query(rule, table_name, date_col, target_date, product_line='tv'):
    """규칙의 쿼리를 실행하고 결과 건수 반환

    예외 처리된 record_id는 결과에서 제외됨
    """
    query_template = rule.get('query', '')
    rule_id = str(rule.get('rule_id', ''))

    if not query_template:
        return 0, []

    if not query_template.strip().upper().startswith('SELECT'):
        return 0, []

    _validate_table_name(table_name)

    # 쿼리 템플릿 변수 치환
    query = query_template.replace('{table}', table_name)
    query = query.replace('{date_col}', date_col)
    query = query.replace('{no_review_texts}', get_all_no_review_texts())
    query = query.replace('{product_line}', product_line)
    if not _validate_select_query(query):
        return 0, []

    # LIKE 절의 %를 %%로 이스케이프 (파라미터 바인딩 충돌 방지)
    # %s 플레이스홀더는 유지하면서 LIKE의 %만 이스케이프
    # 모든 % 를 %%로 변환 후, %s만 다시 복원
    query = query.replace('%', '%%').replace('%%s', '%s')

    try:
        conn = get_dx_connection()
        cursor = conn.cursor()
        cursor.execute(query, (target_date,))
        rows = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description] if cursor.description else []
        cursor.close()
        conn.close()

        # 결과를 dict 리스트로 변환
        results = [dict(zip(columns, row)) for row in rows]

        # cross_detail_mismatch 타입은 Python 후처리로 필터링
        validation_type = rule.get('validation_type', '')
        if validation_type == 'cross_detail_mismatch':
            # product_line 추출 (tv_retail -> tv, hhp_retail -> hhp)
            pl = 'tv' if 'tv' in product_line.lower() else 'hhp'
            # 실제 에러인 행만 필터링 (validate_review_detail_match가 True를 반환하면 에러)
            results = [r for r in results if validate_review_detail_match(r, pl)]

        return len(results), results
    except Exception as e:
        log_error(e)
        return 0, []


def validate_crossfield(target_date, section='tv_retail'):
    """DB 기반 크로스필드 검증 실행

    Args:
        target_date: 검증 대상 날짜
        section: 섹션 코드 (tv_retail, hhp_retail, tv_sentiment, hhp_sentiment, comp_product)
    """
    rules = load_crossfield_rules()
    results = {
        'total_errors': 0,
        'rule_results': []
    }

    table_name = ''
    date_col = ''

    for rule in rules:
        # 해당 section에 적용되는 규칙인지 확인
        if rule.get('section_code', '').lower() != section:
            continue

        # 규칙별 테이블/날짜컬럼 사용 (DB에 저장된 값)
        table_name = rule.get('table_name', '')
        date_col = rule.get('date_column', '')
        _validate_table_name(table_name)

        # 쿼리 실행
        error_count, error_details = execute_crossfield_query(
            rule, table_name, date_col, target_date, section
        )

        results['total_errors'] += error_count
        results['rule_results'].append({
            'rule_id': rule.get('rule_id'),
            'detail_code': rule.get('detail_code'),
            'detail_name': rule.get('detail_name'),
            'field1': rule.get('field1'),
            'field2': rule.get('field2'),
            'validation_type': rule.get('validation_type'),
            'error_message': rule.get('error_message'),
            'error_count': error_count,
            'error_details': error_details,
            'query': rule.get('query', ''),
            'select_fields': rule.get('select_fields', '')
        })

    # 테이블/컬럼 정보도 결과에 포함 (프론트엔드 플레이스홀더 치환용)
    results['table_name'] = table_name
    results['date_col'] = date_col

    return results


def get_status(issue_count, total_count=0, needs_review=False):
    """상태 판정
    - OK: 이상치 0건
    - WARNING: 이상치 1% 미만 또는 10건 이하
    - CRITICAL: 이상치 10건 초과
    - REVIEW_NEEDED: 사람의 검토가 필요한 케이스
    """
    if needs_review:
        return 'REVIEW_NEEDED'
    if issue_count == 0:
        return 'OK'
    elif total_count > 0 and issue_count / total_count < 0.01:
        return 'WARNING'
    elif issue_count <= 10:
        return 'WARNING'
    else:
        return 'CRITICAL'


# ============================================================
# 크로스 필드 논리 검증 함수 (Layer 2에서 이동)
# ============================================================
def validate_cross_field(row_data, account_name='Amazon', product_line='tv'):
    """크로스 필드 논리 검증. 여러 필드 간 관계 검증. 오류 목록 반환"""
    errors = []

    star_rating = row_data.get('star_rating')
    count_of_star_ratings = row_data.get('count_of_star_ratings')
    page_type = row_data.get('page_type')
    main_rank = row_data.get('main_rank')
    bsr_rank = row_data.get('bsr_rank')
    final_sku_price = row_data.get('final_sku_price')
    original_sku_price = row_data.get('original_sku_price')

    # 리테일러별 리뷰없음 텍스트
    if account_name == 'Amazon':
        no_review_texts = ['No customer reviews']
    elif account_name == 'Bestbuy':
        no_review_texts = ['Not yet reviewed']
    else:  # Walmart
        no_review_texts = ['No ratings yet']

    # 1. star_rating 값이 있는데 count_of_star_ratings가 0 또는 NULL
    if star_rating is not None and str(star_rating).strip() != '' and str(star_rating).strip() not in no_review_texts:
        try:
            rating_val = float(star_rating)
            if rating_val > 0:
                if count_of_star_ratings is None or str(count_of_star_ratings).strip() == '':
                    errors.append({
                        'field': 'star_rating ↔ count_of_star_ratings',
                        'value': f'star_rating={star_rating}, count_of_star_ratings=NULL',
                        'error': 'star_rating 값이 있는데 count_of_star_ratings가 NULL'
                    })
                elif str(count_of_star_ratings).strip() not in no_review_texts:
                    clean_count = str(count_of_star_ratings).replace(',', '')
                    if clean_count.isdigit() and int(clean_count) == 0:
                        errors.append({
                            'field': 'star_rating ↔ count_of_star_ratings',
                            'value': f'star_rating={star_rating}, count_of_star_ratings=0',
                            'error': 'star_rating 값이 있는데 count_of_star_ratings가 0'
                        })
        except (ValueError, TypeError):
            pass

    # 2. page_type이 'main'인데 main_rank가 NULL
    if page_type is not None and str(page_type).strip() == 'main':
        if main_rank is None or str(main_rank).strip() == '':
            errors.append({
                'field': 'page_type ↔ main_rank',
                'value': f'page_type=main, main_rank=NULL',
                'error': 'page_type이 main인데 main_rank가 NULL'
            })

    # 3. page_type이 'bsr'인데 bsr_rank가 NULL
    if page_type is not None and str(page_type).strip() == 'bsr':
        if bsr_rank is None or str(bsr_rank).strip() == '':
            errors.append({
                'field': 'page_type ↔ bsr_rank',
                'value': f'page_type=bsr, bsr_rank=NULL',
                'error': 'page_type이 bsr인데 bsr_rank가 NULL'
            })

    # 3-1. page_type이 'promotion'인데 promotion_position이 NULL (TV)
    promotion_position = row_data.get('promotion_position')
    if page_type is not None and str(page_type).strip() == 'promotion':
        if promotion_position is None or str(promotion_position).strip() == '':
            errors.append({
                'field': 'page_type ↔ promotion_position',
                'value': f'page_type=promotion, promotion_position=NULL',
                'error': 'page_type이 promotion인데 promotion_position이 NULL'
            })

    # 3-1-1. promotion_position이 있는데 promotion_type이 NULL (Bestbuy TV/HHP)
    promotion_type = row_data.get('promotion_type')
    if account_name == 'Bestbuy':
        if promotion_position is not None and str(promotion_position).strip() != '':
            if promotion_type is None or str(promotion_type).strip() == '':
                errors.append({
                    'field': 'promotion_position ↔ promotion_type',
                    'value': f'promotion_position={promotion_position}, promotion_type=NULL',
                    'error': 'promotion_position이 있는데 promotion_type이 NULL'
                })

    # 3-2. page_type이 'trend'인데 trend_rank가 NULL (Bestbuy HHP)
    trend_rank = row_data.get('trend_rank')
    if page_type is not None and str(page_type).strip() == 'trend':
        if trend_rank is None or str(trend_rank).strip() == '':
            errors.append({
                'field': 'page_type ↔ trend_rank',
                'value': f'page_type=trend, trend_rank=NULL',
                'error': 'page_type이 trend인데 trend_rank가 NULL'
            })

    # 4. final_sku_price > original_sku_price (할인인데 더 비싼 경우)
    if final_sku_price is not None and original_sku_price is not None:
        final_str = str(final_sku_price).strip()
        original_str = str(original_sku_price).strip()

        if final_str.startswith('$') and original_str.startswith('$'):
            # 월 할부/기간 가격인 경우 할인율 검증 제외 (예: $1.00/month, $5/mo, $10/day)
            is_periodic_price = any(p in final_str.lower() for p in ['/month', '/mo', '/day', '/week', '/yr', '/year'])

            try:
                final_val = float(final_str.replace('$', '').replace(',', '').split('/')[0])
                original_val = float(original_str.replace('$', '').replace(',', '').split('/')[0])

                # 기간 가격이 아닌 경우에만 비교 검증
                if not is_periodic_price:
                    if final_val > original_val:
                        errors.append({
                            'field': 'final_sku_price ↔ original_sku_price',
                            'value': f'final={final_str}, original={original_str}',
                            'error': f'final_sku_price({final_str})가 original_sku_price({original_str})보다 높음'
                        })

                    # 5. 할인율 이상 검증 (90% 이상 할인은 비정상)
                    if original_val > 0 and final_val > 0:
                        discount_rate = (original_val - final_val) / original_val * 100
                        if discount_rate >= 90:
                            errors.append({
                                'field': 'discount_rate',
                                'value': f'final={final_str}, original={original_str}, 할인율={discount_rate:.1f}%',
                                'error': f'할인율이 90% 이상으로 비정상적 ({discount_rate:.1f}%)'
                            })
            except (ValueError, TypeError):
                pass

    # 9. count_of_reviews와 detail_review_content 일관성 검증
    # 리테일러/제품군별 형식:
    # - TV Amazon: "1-", "2-" 형식 (숫자-하이픈)
    # - TV Bestbuy: "|" 구분자 개수 (19개면 20개 리뷰)
    # - TV Walmart: "review1", "review5" 형식
    # - HHP 전체: "review1", "review5" 형식
    count_of_reviews = row_data.get('count_of_reviews')
    detail_review_content = row_data.get('detail_review_content')

    # count_of_reviews 값 파싱
    review_count = 0
    if count_of_reviews is not None:
        try:
            count_str = str(count_of_reviews).strip().replace(',', '')
            if count_str.isdigit():
                review_count = int(count_str)
        except (ValueError, TypeError):
            pass

    # 9-1. count_of_reviews > 0 인데 detail_review_content가 NULL인 경우
    if review_count > 0:
        content_str = str(detail_review_content).strip() if detail_review_content is not None else ''
        if not content_str or content_str.lower() == 'null' or content_str.lower() == 'none':
            errors.append({
                'field': 'count_of_reviews ↔ detail_review_content',
                'value': f'count_of_reviews={review_count}, detail_review_content=NULL',
                'error': f'리뷰 수가 {review_count}개인데 detail_review_content가 NULL임'
            })
        else:
            # 9-2. 둘 다 값이 있을 때 형식 검증
            expected_count = min(review_count, 20)
            has_expected_review = False
            error_detail = ''

            if product_line == 'tv' and account_name == 'Amazon':
                # TV Amazon: "1-", "2-" 형식 확인
                # expected_count번째 리뷰가 있는지 확인 (예: 5개면 "5-" 존재)
                expected_key = f'{expected_count}-'
                if expected_key in content_str:
                    has_expected_review = True
                error_detail = f'{expected_count}-'

            elif product_line == 'tv' and account_name == 'Bestbuy':
                # TV Bestbuy: "|" 구분자 개수로 확인
                # 구분자 n개 = 리뷰 n+1개
                delimiter_count = content_str.count('|')
                actual_review_count = delimiter_count + 1 if delimiter_count >= 0 else 1
                if actual_review_count >= expected_count:
                    has_expected_review = True
                error_detail = f'구분자 {delimiter_count}개 (리뷰 {actual_review_count}개), 기대: {expected_count}개'

            else:
                # TV Walmart, HHP 전체: "review1", "review5" 형식
                expected_key = f'review{expected_count}'
                if expected_key in content_str:
                    has_expected_review = True
                error_detail = expected_key

            if not has_expected_review:
                errors.append({
                    'field': 'count_of_reviews ↔ detail_review_content',
                    'value': f'count_of_reviews={review_count}, {error_detail}=없음',
                    'error': f'리뷰 수가 {review_count}개인데 detail_review_content에 {error_detail}이 없음'
                })

    return errors


def layer_stats(request):
    """Layer 3 통계 API - 이상치 탐지 및 크로스 필드 검증"""
    date_str = request.GET.get('date')
    product_line = request.GET.get('type', 'all')
    section = request.GET.get('section', '')  # 섹션 필터: time_series, cross_field, category_spec, field_missing


    if date_str:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    else:
        target_date = (datetime.now() - timedelta(days=1)).date()

    prev_date = target_date - timedelta(days=1)
    prev_week = target_date - timedelta(days=7)

    results = {
        'timestamp': datetime.now().isoformat(),
        'date': str(target_date),
        'layer': 3,
        'name': '이상치/특수 케이스 검수',
        'product_line': product_line.upper(),
        'checks': [],
        'summary': {
            'total_checked': 0,
            'passed': 0,
            'failed': 0,
            'pass_rate': 0,
            'status': 'OK'
        }
    }

    total_checked = 0
    total_anomalies = 0

    # 변수 초기화
    tv_total = 0
    hhp_total = 0
    yt_comment_total = 0

    try:
        conn = get_dx_connection()
        cursor = conn.cursor()

        # 섹션별 실행 대상 결정
        run_timeseries = section in ('', 'time_series')
        run_crossfield = section in ('', 'cross_field')
        run_catspec = section in ('', 'category_spec')
        run_market = section in ('', 'category_spec', 'cross_field')

        # ============================================================
        # 1. 시계열 이상치 탐지 (DB 기반 - 전일 대비 급격한 변화)
        # ============================================================
        timeseries_rules = load_timeseries_rules() if run_timeseries else []

        # 제품라인별로 필터링
        if product_line != 'all':
            timeseries_rules = [r for r in timeseries_rules if r['product_line'] == product_line]

        # 테이블별 전체 건수 캐시
        table_totals = {}

        # HHP용 별도 커넥션 (TV와 데이터 타입 충돌 방지)
        hhp_conn = None
        hhp_cursor = None

        for rule in timeseries_rules:
            table_name = rule['table_name']
            _validate_table_name(table_name)
            date_column = rule['date_column']
            check_type = rule['check_type']
            pl = rule['product_line']

            # HHP는 별도 커넥션 사용
            if pl == 'hhp':
                if hhp_conn is None:
                    hhp_conn = get_dx_connection()
                    hhp_cursor = hhp_conn.cursor()
                curr_cursor = hhp_cursor
            else:
                curr_cursor = cursor

            # 테이블 전체 건수 조회 (캐시)
            if table_name not in table_totals:
                try:
                    curr_cursor.execute(f"""
                        SELECT COUNT(*) FROM {table_name}
                        WHERE DATE({date_column}::timestamp) = %s
                    """, (target_date,))
                    table_totals[table_name] = curr_cursor.fetchone()[0] or 0
                except Exception as e:
                    log_error(e)
                    table_totals[table_name] = 0

            table_total = table_totals[table_name]

            # DB 저장 쿼리 실행
            anomaly_count = 0
            try:
                stored_query = rule.get('query', '')
                if stored_query:
                    curr_cursor.execute(stored_query, (target_date, target_date, prev_date))
                    anomaly_count = curr_cursor.fetchone()[0] or 0
            except Exception as e:
                log_error(e)

            total_checked += table_total
            total_anomalies += anomaly_count

            # 임계값 표시 문자열
            if check_type == 'price':
                threshold_str = f">{int(rule['threshold_pct'])}%"
            else:
                threshold_str = f"+{int(rule['threshold_pct'])}%"

            results['checks'].append({
                'category': '시계열 이상치',
                'name': rule['detail_name'],
                'description': rule['error_message'],
                'checked': table_total,
                'passed': table_total - anomaly_count,
                'failed': anomaly_count,
                'threshold': threshold_str,
                'status': get_status(anomaly_count, table_total, needs_review=(check_type == 'review' and anomaly_count > 0))
            })

        # TV/HHP 전체 건수 저장 (크로스 필드에서 사용)
        tv_total = table_totals.get('tv_retail_com', 0)
        hhp_total = table_totals.get('hhp_retail_com', 0)

        if run_crossfield:
            # TV 전체 건수가 없으면 직접 조회
            if tv_total == 0 and product_line in ['tv', 'all']:
                try:
                    cursor.execute("""
                        SELECT COUNT(*) FROM tv_retail_com
                        WHERE DATE(crawl_datetime::timestamp) = %s
                    """, (target_date,))
                    tv_total = cursor.fetchone()[0] or 0
                    table_totals['tv_retail_com'] = tv_total
                except:
                    pass

            # HHP 전체 건수가 없으면 직접 조회
            if hhp_total == 0 and product_line in ['hhp', 'all']:
                if hhp_conn is None:
                    hhp_conn = get_dx_connection()
                    hhp_cursor = hhp_conn.cursor()
                try:
                    hhp_cursor.execute("""
                        SELECT COUNT(*) FROM hhp_retail_com
                        WHERE DATE(crawl_strdatetime) = %s
                    """, (target_date,))
                    hhp_total = hhp_cursor.fetchone()[0] or 0
                    table_totals['hhp_retail_com'] = hhp_total
                except:
                    pass

        # ============================================================
        # 2. 크로스 필드 논리 검증 (DB 기반)
        # ============================================================
        if run_crossfield and product_line in ['tv', 'all']:
            # TV Retail 크로스 필드 검증 - DB 기반 쿼리 실행
            tv_cross_total = tv_total
            try:
                tv_crossfield_result = validate_crossfield(target_date, 'tv_retail')
                tv_cross_errors = tv_crossfield_result['total_errors']
            except Exception as e:
                log_error(e)
                tv_cross_errors = 0

            total_checked += tv_cross_total
            total_anomalies += tv_cross_errors

            results['checks'].append({
                'category': '크로스 필드 검증',
                'name': 'TV 논리적 일관성',
                'description': 'star_rating↔count, page_type↔rank, 가격, count_of_reviews↔detail_review_content 검증',
                'checked': tv_cross_total,
                'passed': tv_cross_total - tv_cross_errors,
                'failed': tv_cross_errors,
                'status': get_status(tv_cross_errors, tv_cross_total)
            })

        if run_crossfield and product_line in ['hhp', 'all']:
            # HHP Retail 크로스 필드 검증 - DB 기반 쿼리 실행
            hhp_cross_total = hhp_total
            try:
                hhp_crossfield_result = validate_crossfield(target_date, 'hhp_retail')
                hhp_cross_errors = hhp_crossfield_result['total_errors']
            except Exception as e:
                log_error(e)
                hhp_cross_errors = 0

            total_checked += hhp_cross_total
            total_anomalies += hhp_cross_errors

            results['checks'].append({
                'category': '크로스 필드 검증',
                'name': 'HHP 논리적 일관성',
                'description': 'star_rating↔count, page_type↔rank, 가격, count_of_reviews↔detail_review_content 검증',
                'checked': hhp_cross_total,
                'passed': hhp_cross_total - hhp_cross_errors,
                'failed': hhp_cross_errors,
                'status': get_status(hhp_cross_errors, hhp_cross_total)
            })

        # ---------------------------------------------------------
        # 2-3. Sentiment ↔ Retail 리뷰 수 일관성 검증
        # 기준: sentiment 점수가 있는데 원본 retail의 리뷰 수가 0인 경우
        # ---------------------------------------------------------
        if run_crossfield and product_line in ['tv', 'all']:
            tv_sentiment_cross_total = 0
            tv_sentiment_cross_anomaly = 0
            try:
                sent_conn = get_dx_connection()
                sent_cursor = sent_conn.cursor()

                # TV Sentiment 전체 건수 (sentiment_score가 실제 값인 것만, None/none 문자열 제외)
                sent_cursor.execute("""
                    SELECT COUNT(*)
                    FROM tv_retail_sentiment s
                    JOIN tv_retail_com r ON s.retail_com_id = r.id
                    WHERE DATE(r.crawl_datetime::timestamp) = %s
                    AND s.sentiment_score IS NOT NULL
                    AND LOWER(s.sentiment_score::text) NOT IN ('none', 'null', '')
                """, (target_date,))
                tv_sentiment_cross_total = sent_cursor.fetchone()[0] or 0

                # sentiment 점수가 있는데 리뷰 수가 0인 경우
                sent_cursor.execute("""
                    SELECT COUNT(*)
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
                """, (target_date,))
                tv_sentiment_cross_anomaly = sent_cursor.fetchone()[0] or 0

                sent_cursor.close()
                sent_conn.close()
            except Exception as e:
                log_error(e)

            total_checked += tv_sentiment_cross_total
            total_anomalies += tv_sentiment_cross_anomaly

            results['checks'].append({
                'category': '크로스 필드 검증',
                'name': 'TV Sentiment↔리뷰 일관성',
                'description': 'sentiment 점수가 있는데 원본 리뷰 수가 NULL/빈값/0/리뷰없음',
                'checked': tv_sentiment_cross_total,
                'passed': tv_sentiment_cross_total - tv_sentiment_cross_anomaly,
                'failed': tv_sentiment_cross_anomaly,
                'status': get_status(tv_sentiment_cross_anomaly, tv_sentiment_cross_total)
            })

        if run_crossfield and product_line in ['hhp', 'all']:
            hhp_sentiment_cross_total = 0
            hhp_sentiment_cross_anomaly = 0
            try:
                sent_conn = get_dx_connection()
                sent_cursor = sent_conn.cursor()

                # HHP Sentiment 전체 건수 (sentiment_score가 실제 값인 것만, None/none 문자열 제외)
                # crawl_strdatetime을 timestamp로 캐스팅하여 날짜 비교
                sent_cursor.execute("""
                    SELECT COUNT(*)
                    FROM hhp_retail_sentiment s
                    JOIN hhp_retail_com r ON s.retail_com_id = r.id
                    WHERE DATE(r.crawl_strdatetime::timestamp) = %s
                    AND s.sentiment_score IS NOT NULL
                    AND LOWER(s.sentiment_score::text) NOT IN ('none', 'null', '')
                """, (target_date,))
                hhp_sentiment_cross_total = sent_cursor.fetchone()[0] or 0

                # sentiment 점수가 있는데 리뷰 수가 0인 경우
                sent_cursor.execute("""
                    SELECT COUNT(*)
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
                """, (target_date,))
                hhp_sentiment_cross_anomaly = sent_cursor.fetchone()[0] or 0

                sent_cursor.close()
                sent_conn.close()
            except Exception as e:
                log_error(e)

            total_checked += hhp_sentiment_cross_total
            total_anomalies += hhp_sentiment_cross_anomaly

            results['checks'].append({
                'category': '크로스 필드 검증',
                'name': 'HHP Sentiment↔리뷰 일관성',
                'description': 'sentiment 점수가 있는데 원본 리뷰 수가 NULL/빈값/0/리뷰없음',
                'checked': hhp_sentiment_cross_total,
                'passed': hhp_sentiment_cross_total - hhp_sentiment_cross_anomaly,
                'failed': hhp_sentiment_cross_anomaly,
                'status': get_status(hhp_sentiment_cross_anomaly, hhp_sentiment_cross_total)
            })

        # ============================================================
        # 3. 카테고리별 특성 기반 검증 (DB 규칙 기반, 동적 처리)
        # ============================================================
        if run_catspec:
            try:
                category_spec_results = validate_all_category_specs(target_date)
                for cat_result in category_spec_results:
                    # product_line 필터링
                    sec_code = cat_result.get('section_code', '').lower()
                    if product_line == 'tv' and 'hhp' in sec_code:
                        continue
                    if product_line == 'hhp' and 'tv' in sec_code and 'hhp' not in sec_code:
                        continue
                    if product_line not in ['market', 'all'] and 'market' in sec_code:
                        continue

                    cat_total = cat_result.get('total', 0)
                    cat_anomaly = cat_result.get('anomaly', 0)

                    total_checked += cat_total
                    total_anomalies += cat_anomaly

                    results['checks'].append({
                        'category': '카테고리별 특성',
                        'name': cat_result.get('section_name', sec_code),
                        'description': cat_result.get('description', ''),
                        'checked': cat_total,
                        'passed': cat_total - cat_anomaly,
                        'failed': cat_anomaly,
                        'status': get_status(cat_anomaly, cat_total)
                    })
            except Exception as e:
                log_error(e)

        # ============================================================
        # 4. Market 검증 (market 타입 또는 all인 경우)
        # ============================================================
        if run_market and product_line in ['market', 'all']:
            market_conn = get_dx_connection()
            market_cursor = market_conn.cursor()

            # 월 범위 계산 (조건부 수집 테이블용 - Layer 1과 동일한 방식)
            first_day_of_month = target_date.replace(day=1)
            month_start = first_day_of_month.strftime('%Y-%m-%d')
            if target_date.month == 12:
                month_end_date = target_date.replace(year=target_date.year + 1, month=1, day=1) - timedelta(days=1)
            else:
                month_end_date = target_date.replace(month=target_date.month + 1, day=1) - timedelta(days=1)
            month_end = month_end_date.strftime('%Y-%m-%d')

            # ---------------------------------------------------------
            # 5-1. market_comp_product 크로스 필드 검증
            # 기준: samsung_series_name과 comp_brand가 동일한 경우 (자사 vs 경쟁사 오류)
            # 참고: 분기별 수집이므로 월 범위에서 최근 batch_id로 조회
            # ---------------------------------------------------------
            comp_product_total = 0
            comp_product_cross_anomaly = 0
            comp_product_batch_id = None
            try:
                # 해당 월에 실행된 comp_product 배치 조회
                market_cursor.execute("""
                    SELECT batch_id, MAX(created_at) as last_run
                    FROM market_comp_product
                    WHERE batch_id IS NOT NULL
                      AND created_at >= %s AND created_at < %s::date + INTERVAL '1 day'
                    GROUP BY batch_id
                    ORDER BY last_run DESC
                    LIMIT 1
                """, (month_start, month_end))
                batch_row = market_cursor.fetchone()
                comp_product_batch_id = batch_row[0] if batch_row else None

                if comp_product_batch_id:
                    market_cursor.execute("""
                        SELECT COUNT(*) FROM market_comp_product
                        WHERE batch_id = %s
                    """, (comp_product_batch_id,))
                    comp_product_total = market_cursor.fetchone()[0] or 0
                    market_cursor.execute("""
                        SELECT COUNT(*) FROM market_comp_product
                        WHERE batch_id = %s
                        AND LOWER(samsung_series_name) LIKE '%%' || LOWER(comp_brand) || '%%'
                    """, (comp_product_batch_id,))
                    comp_product_cross_anomaly = market_cursor.fetchone()[0] or 0
            except Exception as e:
                log_error(e)

            total_anomalies += comp_product_cross_anomaly

            results['checks'].append({
                'category': '크로스 필드 검증',
                'name': 'Comp Product 자사/경쟁사 구분',
                'description': 'samsung_series_name에 comp_brand가 포함된 논리 오류',
                'checked': comp_product_total,
                'passed': comp_product_total - comp_product_cross_anomaly,
                'failed': comp_product_cross_anomaly,
                'status': get_status(comp_product_cross_anomaly, comp_product_total)
            })

            # Forecast는 카테고리별 특성에서 처리됨

            # Market 커넥션 닫기
            market_cursor.close()
            market_conn.close()

        # HHP 커넥션 닫기
        if hhp_conn is not None:
            hhp_cursor.close()
            hhp_conn.close()

        # 메인 커넥션 닫기 (항상 열려 있음)
        cursor.close()
        conn.close()

    except Exception as e:
        results['error'] = log_error(e)

    # Summary 계산 - checks 배열에서 합산
    summary_checked = sum(check.get('checked', 0) for check in results['checks'])
    summary_failed = sum(check.get('failed', 0) for check in results['checks'])
    summary_passed = summary_checked - summary_failed

    results['summary'] = {
        'total_checked': summary_checked,
        'passed': summary_passed,
        'failed': summary_failed,
        'pass_rate': round((summary_passed / summary_checked * 100), 2) if summary_checked > 0 else 0,
        'status': 'OK' if summary_failed == 0 else ('WARNING' if summary_failed < summary_checked * 0.05 else 'CRITICAL')
    }

    return JsonResponse(results)


def cross_field_detail(request):
    """크로스 필드 논리 검증 상세 API (DB 기반) - 검증 유형별 요약"""
    date_str = request.GET.get('date')
    product_line = request.GET.get('type', 'tv')
    rule_id = request.GET.get('rule_id')  # 특정 규칙 상세 조회 시

    if date_str:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    else:
        target_date = (datetime.now() - timedelta(days=1)).date()

    # product_line을 section으로 변환
    section_map = {'tv': 'tv_retail', 'hhp': 'hhp_retail'}
    section = section_map.get(product_line, f'{product_line}_retail')

    try:
        # DB 기반 크로스필드 검증 실행
        crossfield_result = validate_crossfield(target_date, section)

        # 특정 규칙 상세 조회
        if rule_id:
            for rule_result in crossfield_result['rule_results']:
                if str(rule_result['rule_id']) == str(rule_id):
                    # 해당 규칙의 상세 데이터 반환
                    anomalies = []
                    validation_type = rule_result.get('validation_type', '')

                    for detail in rule_result['error_details']:
                        # 모든 컬럼 포함
                        anomaly = {
                            'item': detail.get('item'),
                            'account_name': detail.get('account_name'),
                            'page_type': detail.get('page_type'),
                        }
                        # 쿼리 결과의 모든 컬럼 추가
                        for key, value in detail.items():
                            if key not in ['item', 'account_name', 'page_type']:
                                anomaly[key] = value

                        # cross_detail_mismatch 타입이면 validation_tag 추가
                        if validation_type == 'cross_detail_mismatch':
                            validation_info = validate_review_detail_match(detail, product_line, return_detail=True)
                            anomaly['validation_tag'] = validation_info.get('reason', '')
                            anomaly['expected_pattern'] = validation_info.get('expected_pattern', '')

                        anomalies.append(anomaly)

                    # account_name, item, crawl_datetime 순으로 정렬
                    anomalies.sort(key=lambda x: (
                        x.get('account_name', '') or '',
                        x.get('item', '') or '',
                        str(x.get('crawl_datetime', '') or x.get('crawl_strdatetime', '') or '')
                    ))

                    return JsonResponse({
                        'date': str(target_date),
                        'product_line': product_line.upper(),
                        'rule_id': rule_result['rule_id'],
                        'detail_code': rule_result['detail_code'],
                        'field1': rule_result['field1'],
                        'field2': rule_result.get('field2'),
                        'validation_type': validation_type,
                        'error_message': rule_result['error_message'],
                        'total_anomalies': rule_result['error_count'],
                        'anomalies': anomalies,
                        'select_fields': rule_result.get('select_fields', '')
                    })

            return JsonResponse({'error': '해당 규칙을 찾을 수 없습니다.'})

        # 규칙별 요약 반환 (검증 유형별 건수) - 0건도 포함
        rule_summary = []
        total_anomalies = 0
        for r in crossfield_result['rule_results']:
            rule_summary.append({
                'rule_id': r['rule_id'],
                'detail_code': r['detail_code'],
                'field1': r['field1'],
                'field2': r.get('field2'),
                'validation_type': r.get('validation_type', ''),
                'error_message': r['error_message'],
                'error_count': r['error_count'],
                'query': r.get('query', ''),
                'select_fields': r.get('select_fields', '')
            })
            total_anomalies += r['error_count']

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


def time_series_detail(request):
    """시계열 이상치 상세 API"""
    date_str = request.GET.get('date')
    product_line = request.GET.get('type', 'tv')
    check_type = request.GET.get('check', 'price')  # price, rank
    period = request.GET.get('period', 'daily')  # daily, weekly

    if date_str:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    else:
        target_date = (datetime.now() - timedelta(days=1)).date()

    if period == 'weekly':
        compare_date = target_date - timedelta(days=7)
        threshold = 0.5
    else:
        compare_date = target_date - timedelta(days=1)
        threshold = 0.5  # 50% 초과

    try:
        conn = get_dx_connection()
        cursor = conn.cursor()

        if product_line == 'tv':
            if check_type == 'price':
                # TV 가격 - 오전/오후 구분 비교 (문자열 가격을 숫자로 변환)
                cursor.execute("""
                    WITH today_am AS (
                        SELECT item, account_name, retailer_sku_name,
                               final_sku_price as price_str,
                               CAST(REPLACE(REPLACE(SPLIT_PART(REPLACE(final_sku_price, '$', ''), '/', 1), ',', ''), ' ', '') AS NUMERIC) as price,
                               crawl_datetime, product_url, 'AM' as period
                        FROM tv_retail_com
                        WHERE DATE(crawl_datetime::timestamp) = %s
                        AND EXTRACT(HOUR FROM crawl_datetime::timestamp) < 12
                        AND final_sku_price IS NOT NULL
                        AND final_sku_price LIKE '$%%'
                        AND REPLACE(REPLACE(SPLIT_PART(REPLACE(final_sku_price, '$', ''), '/', 1), ',', ''), ' ', '') ~ '^[0-9.]+$'
                    ),
                    today_pm AS (
                        SELECT item, account_name, retailer_sku_name,
                               final_sku_price as price_str,
                               CAST(REPLACE(REPLACE(SPLIT_PART(REPLACE(final_sku_price, '$', ''), '/', 1), ',', ''), ' ', '') AS NUMERIC) as price,
                               crawl_datetime, product_url, 'PM' as period
                        FROM tv_retail_com
                        WHERE DATE(crawl_datetime::timestamp) = %s
                        AND EXTRACT(HOUR FROM crawl_datetime::timestamp) >= 12
                        AND final_sku_price IS NOT NULL
                        AND final_sku_price LIKE '$%%'
                        AND REPLACE(REPLACE(SPLIT_PART(REPLACE(final_sku_price, '$', ''), '/', 1), ',', ''), ' ', '') ~ '^[0-9.]+$'
                    ),
                    yesterday_pm AS (
                        SELECT item, account_name,
                               final_sku_price as price_str,
                               CAST(REPLACE(REPLACE(SPLIT_PART(REPLACE(final_sku_price, '$', ''), '/', 1), ',', ''), ' ', '') AS NUMERIC) as price
                        FROM tv_retail_com
                        WHERE DATE(crawl_datetime::timestamp) = %s
                        AND EXTRACT(HOUR FROM crawl_datetime::timestamp) >= 12
                        AND final_sku_price IS NOT NULL
                        AND final_sku_price LIKE '$%%'
                        AND REPLACE(REPLACE(SPLIT_PART(REPLACE(final_sku_price, '$', ''), '/', 1), ',', ''), ' ', '') ~ '^[0-9.]+$'
                    ),
                    am_changes AS (
                        SELECT t.item, t.account_name, t.retailer_sku_name,
                               y.price_str as prev_price, t.price_str as curr_price,
                               ROUND(((t.price - y.price) / NULLIF(y.price, 0) * 100)::numeric, 2) as change_pct,
                               t.crawl_datetime, t.product_url, t.period,
                               ABS(t.price - y.price) / NULLIF(y.price, 0) as abs_change
                        FROM today_am t
                        JOIN yesterday_pm y ON t.item = y.item AND t.account_name = y.account_name
                        WHERE t.price > 0 AND y.price > 0
                        AND ABS(t.price - y.price) / NULLIF(y.price, 0) > %s
                    ),
                    pm_changes AS (
                        SELECT t.item, t.account_name, t.retailer_sku_name,
                               a.price_str as prev_price, t.price_str as curr_price,
                               ROUND(((t.price - a.price) / NULLIF(a.price, 0) * 100)::numeric, 2) as change_pct,
                               t.crawl_datetime, t.product_url, t.period,
                               ABS(t.price - a.price) / NULLIF(a.price, 0) as abs_change
                        FROM today_pm t
                        JOIN today_am a ON t.item = a.item AND t.account_name = a.account_name
                        WHERE t.price > 0 AND a.price > 0
                        AND ABS(t.price - a.price) / NULLIF(a.price, 0) > %s
                    )
                    SELECT item, account_name, retailer_sku_name, prev_price, curr_price, change_pct, crawl_datetime, product_url, period
                    FROM (
                        SELECT * FROM am_changes
                        UNION ALL
                        SELECT * FROM pm_changes
                    ) combined
                    ORDER BY abs_change DESC
                """, (target_date, target_date, compare_date, threshold, threshold))
            else:  # rank
                # TV 순위 - 오전/오후 구분 비교
                cursor.execute("""
                    WITH today_am AS (
                        SELECT item, account_name, retailer_sku_name, main_rank, crawl_datetime, product_url, 'AM' as period
                        FROM tv_retail_com
                        WHERE DATE(crawl_datetime::timestamp) = %s
                        AND EXTRACT(HOUR FROM crawl_datetime::timestamp) < 12
                        AND main_rank IS NOT NULL
                    ),
                    today_pm AS (
                        SELECT item, account_name, retailer_sku_name, main_rank, crawl_datetime, product_url, 'PM' as period
                        FROM tv_retail_com
                        WHERE DATE(crawl_datetime::timestamp) = %s
                        AND EXTRACT(HOUR FROM crawl_datetime::timestamp) >= 12
                        AND main_rank IS NOT NULL
                    ),
                    yesterday_pm AS (
                        SELECT item, account_name, main_rank
                        FROM tv_retail_com
                        WHERE DATE(crawl_datetime::timestamp) = %s
                        AND EXTRACT(HOUR FROM crawl_datetime::timestamp) >= 12
                        AND main_rank IS NOT NULL
                    ),
                    am_changes AS (
                        SELECT t.item, t.account_name, t.retailer_sku_name,
                               y.main_rank as prev_rank, t.main_rank as curr_rank,
                               (t.main_rank - y.main_rank) as rank_change,
                               t.crawl_datetime, t.product_url, t.period,
                               ABS(t.main_rank - y.main_rank) as abs_change
                        FROM today_am t
                        JOIN yesterday_pm y ON t.item = y.item AND t.account_name = y.account_name
                        WHERE ABS(t.main_rank - y.main_rank) > 50
                    ),
                    pm_changes AS (
                        SELECT t.item, t.account_name, t.retailer_sku_name,
                               a.main_rank as prev_rank, t.main_rank as curr_rank,
                               (t.main_rank - a.main_rank) as rank_change,
                               t.crawl_datetime, t.product_url, t.period,
                               ABS(t.main_rank - a.main_rank) as abs_change
                        FROM today_pm t
                        JOIN today_am a ON t.item = a.item AND t.account_name = a.account_name
                        WHERE ABS(t.main_rank - a.main_rank) > 50
                    )
                    SELECT item, account_name, retailer_sku_name, prev_rank, curr_rank, rank_change, crawl_datetime, product_url, period
                    FROM (
                        SELECT * FROM am_changes
                        UNION ALL
                        SELECT * FROM pm_changes
                    ) combined
                    ORDER BY abs_change DESC
                """, (target_date, target_date, compare_date))
        else:
            if check_type == 'price':
                # HHP 가격 - 오전/오후 구분 비교
                # 오전(AM)은 전일 오후(PM)와, 오후(PM)는 당일 오전(AM)과 비교
                cursor.execute("""
                    WITH today_am AS (
                        SELECT item, account_name, retailer_sku_name,
                               final_sku_price as price_str,
                               CAST(REPLACE(REPLACE(SPLIT_PART(REPLACE(final_sku_price, '$', ''), '/', 1), ',', ''), ' ', '') AS NUMERIC) as price,
                               crawl_strdatetime,
                               product_url,
                               'AM' as period
                        FROM hhp_retail_com
                        WHERE DATE(crawl_strdatetime::timestamp) = %s
                        AND EXTRACT(HOUR FROM crawl_strdatetime::timestamp) < 12
                        AND final_sku_price IS NOT NULL
                        AND final_sku_price LIKE '$%%'
                    ),
                    today_pm AS (
                        SELECT item, account_name, retailer_sku_name,
                               final_sku_price as price_str,
                               CAST(REPLACE(REPLACE(SPLIT_PART(REPLACE(final_sku_price, '$', ''), '/', 1), ',', ''), ' ', '') AS NUMERIC) as price,
                               crawl_strdatetime,
                               product_url,
                               'PM' as period
                        FROM hhp_retail_com
                        WHERE DATE(crawl_strdatetime::timestamp) = %s
                        AND EXTRACT(HOUR FROM crawl_strdatetime::timestamp) >= 12
                        AND final_sku_price IS NOT NULL
                        AND final_sku_price LIKE '$%%'
                    ),
                    yesterday_pm AS (
                        SELECT item, account_name,
                               final_sku_price as price_str,
                               CAST(REPLACE(REPLACE(SPLIT_PART(REPLACE(final_sku_price, '$', ''), '/', 1), ',', ''), ' ', '') AS NUMERIC) as price
                        FROM hhp_retail_com
                        WHERE DATE(crawl_strdatetime::timestamp) = %s
                        AND EXTRACT(HOUR FROM crawl_strdatetime::timestamp) >= 12
                        AND final_sku_price IS NOT NULL
                        AND final_sku_price LIKE '$%%'
                    ),
                    am_changes AS (
                        SELECT t.item, t.account_name, t.retailer_sku_name as product_name,
                               y.price_str as prev_price, t.price_str as curr_price,
                               ROUND(((t.price - y.price) / NULLIF(y.price, 0) * 100)::numeric, 2) as change_pct,
                               t.crawl_strdatetime, t.product_url, t.period,
                               ABS(t.price - y.price) / NULLIF(y.price, 0) as abs_change
                        FROM today_am t
                        JOIN yesterday_pm y ON t.item = y.item AND t.account_name = y.account_name
                        WHERE t.price > 0 AND y.price > 0
                        AND ABS(t.price - y.price) / NULLIF(y.price, 0) > %s
                    ),
                    pm_changes AS (
                        SELECT t.item, t.account_name, t.retailer_sku_name as product_name,
                               a.price_str as prev_price, t.price_str as curr_price,
                               ROUND(((t.price - a.price) / NULLIF(a.price, 0) * 100)::numeric, 2) as change_pct,
                               t.crawl_strdatetime, t.product_url, t.period,
                               ABS(t.price - a.price) / NULLIF(a.price, 0) as abs_change
                        FROM today_pm t
                        JOIN today_am a ON t.item = a.item AND t.account_name = a.account_name
                        WHERE t.price > 0 AND a.price > 0
                        AND ABS(t.price - a.price) / NULLIF(a.price, 0) > %s
                    )
                    SELECT item, account_name, product_name, prev_price, curr_price, change_pct, crawl_strdatetime, product_url, period
                    FROM (
                        SELECT * FROM am_changes
                        UNION ALL
                        SELECT * FROM pm_changes
                    ) combined
                    ORDER BY abs_change DESC
                """, (target_date, target_date, compare_date, threshold, threshold))
            else:  # rank
                # HHP 순위 - 오전/오후 구분 비교
                cursor.execute("""
                    WITH today_am AS (
                        SELECT item, account_name, main_rank, crawl_strdatetime, product_url, 'AM' as period
                        FROM hhp_retail_com
                        WHERE DATE(crawl_strdatetime::timestamp) = %s
                        AND EXTRACT(HOUR FROM crawl_strdatetime::timestamp) < 12
                        AND main_rank IS NOT NULL
                    ),
                    today_pm AS (
                        SELECT item, account_name, main_rank, crawl_strdatetime, product_url, 'PM' as period
                        FROM hhp_retail_com
                        WHERE DATE(crawl_strdatetime::timestamp) = %s
                        AND EXTRACT(HOUR FROM crawl_strdatetime::timestamp) >= 12
                        AND main_rank IS NOT NULL
                    ),
                    yesterday_pm AS (
                        SELECT item, account_name, main_rank
                        FROM hhp_retail_com
                        WHERE DATE(crawl_strdatetime::timestamp) = %s
                        AND EXTRACT(HOUR FROM crawl_strdatetime::timestamp) >= 12
                        AND main_rank IS NOT NULL
                    ),
                    am_changes AS (
                        SELECT t.item, t.account_name, t.item as product_name,
                               y.main_rank as prev_rank, t.main_rank as curr_rank,
                               (t.main_rank - y.main_rank) as rank_change,
                               t.crawl_strdatetime, t.product_url, t.period,
                               ABS(t.main_rank - y.main_rank) as abs_change
                        FROM today_am t
                        JOIN yesterday_pm y ON t.item = y.item AND t.account_name = y.account_name
                        WHERE ABS(t.main_rank - y.main_rank) > 50
                    ),
                    pm_changes AS (
                        SELECT t.item, t.account_name, t.item as product_name,
                               a.main_rank as prev_rank, t.main_rank as curr_rank,
                               (t.main_rank - a.main_rank) as rank_change,
                               t.crawl_strdatetime, t.product_url, t.period,
                               ABS(t.main_rank - a.main_rank) as abs_change
                        FROM today_pm t
                        JOIN today_am a ON t.item = a.item AND t.account_name = a.account_name
                        WHERE ABS(t.main_rank - a.main_rank) > 50
                    )
                    SELECT item, account_name, product_name, prev_rank, curr_rank, rank_change, crawl_strdatetime, product_url, period
                    FROM (
                        SELECT * FROM am_changes
                        UNION ALL
                        SELECT * FROM pm_changes
                    ) combined
                    ORDER BY abs_change DESC
                """, (target_date, target_date, compare_date))

        rows = cursor.fetchall()
        changes = []

        if check_type == 'price':
            for row in rows:
                changes.append({
                    'item': row[0],
                    'account_name': row[1],
                    'product_name': str(row[2])[:50] + '...' if row[2] and len(str(row[2])) > 50 else row[2],
                    'prev_price': row[3],
                    'curr_price': row[4],
                    'change_pct': float(row[5]) if row[5] else None,
                    'crawl_datetime': str(row[6]),
                    'product_url': row[7] if len(row) > 7 else None,
                    'period': row[8] if len(row) > 8 else None  # AM/PM
                })
        else:
            for row in rows:
                changes.append({
                    'item': row[0],
                    'account_name': row[1],
                    'product_name': str(row[2])[:50] + '...' if row[2] and len(str(row[2])) > 50 else row[2],
                    'prev_rank': row[3],
                    'curr_rank': row[4],
                    'rank_change': row[5],
                    'crawl_datetime': str(row[6]),
                    'product_url': row[7] if len(row) > 7 else None,
                    'period': row[8] if len(row) > 8 else None  # AM/PM
                })

        cursor.close()
        conn.close()

        return JsonResponse({
            'date': str(target_date),
            'compare_date': str(compare_date),
            'product_line': product_line.upper(),
            'check_type': check_type,
            'period': period,
            'threshold': f'{threshold * 100}%' if check_type == 'price' else '50위',
            'total_changes': len(changes),
            'changes': changes
        })

    except Exception as e:
        log_error(e)
        return safe_error(e, changes=[])


def duplicate_detail(request):
    """중복 변형 탐지 상세 API - 같은 수집 시점(AM/PM) 내 중복만 표시"""
    date_str = request.GET.get('date')
    product_line = request.GET.get('type', 'tv')

    if date_str:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    else:
        target_date = (datetime.now() - timedelta(days=1)).date()

    try:
        conn = get_dx_connection()
        cursor = conn.cursor()

        if product_line == 'tv':
            cursor.execute("""
                SELECT item, account_name, page_type,
                       CASE WHEN EXTRACT(HOUR FROM crawl_datetime::timestamp) < 12 THEN 'AM' ELSE 'PM' END as period,
                       COUNT(*) as cnt,
                       MIN(crawl_datetime) as first_crawl,
                       MAX(crawl_datetime) as last_crawl
                FROM tv_retail_com
                WHERE DATE(crawl_datetime::timestamp) = %s
                GROUP BY item, account_name, page_type,
                         CASE WHEN EXTRACT(HOUR FROM crawl_datetime::timestamp) < 12 THEN 'AM' ELSE 'PM' END
                HAVING COUNT(*) > 1
                ORDER BY COUNT(*) DESC
            """, (target_date,))
        elif product_line == 'hhp':
            cursor.execute("""
                SELECT item, account_name, page_type,
                       CASE WHEN EXTRACT(HOUR FROM crawl_strdatetime::timestamp) < 12 THEN 'AM' ELSE 'PM' END as period,
                       COUNT(*) as cnt,
                       MIN(crawl_strdatetime) as first_crawl,
                       MAX(crawl_strdatetime) as last_crawl
                FROM hhp_retail_com
                WHERE DATE(crawl_strdatetime) = %s
                GROUP BY item, account_name, page_type,
                         CASE WHEN EXTRACT(HOUR FROM crawl_strdatetime::timestamp) < 12 THEN 'AM' ELSE 'PM' END
                HAVING COUNT(*) > 1
                ORDER BY COUNT(*) DESC
            """, (target_date,))
        else:  # youtube
            cursor.execute("""
                SELECT video_id, comment_id,
                       CASE WHEN EXTRACT(HOUR FROM created_at::timestamp) < 12 THEN 'AM' ELSE 'PM' END as period,
                       COUNT(*) as cnt,
                       MIN(created_at) as first_crawl,
                       MAX(created_at) as last_crawl
                FROM youtube_comments
                WHERE DATE(created_at) = %s
                GROUP BY video_id, comment_id,
                         CASE WHEN EXTRACT(HOUR FROM created_at::timestamp) < 12 THEN 'AM' ELSE 'PM' END
                HAVING COUNT(*) > 1
                ORDER BY COUNT(*) DESC
            """, (target_date,))

        rows = cursor.fetchall()
        duplicates = []

        if product_line in ['tv', 'hhp']:
            for row in rows:
                period_text = '오전' if row[3] == 'AM' else '오후'
                duplicates.append({
                    'item': row[0],
                    'account_name': row[1],
                    'page_type': row[2],
                    'period': period_text,
                    'count': row[4],
                    'first_crawl': str(row[5]),
                    'last_crawl': str(row[6])
                })
        else:
            for row in rows:
                period_text = '오전' if row[2] == 'AM' else '오후'
                duplicates.append({
                    'video_id': row[0],
                    'comment_id': row[1],
                    'period': period_text,
                    'count': row[3],
                    'first_crawl': str(row[4]),
                    'last_crawl': str(row[5])
                })

        cursor.close()
        conn.close()

        return JsonResponse({
            'date': str(target_date),
            'product_line': product_line.upper(),
            'total_duplicates': len(duplicates),
            'duplicates': duplicates
        })

    except Exception as e:
        return safe_error(e)


def review_change_detail(request):
    """리뷰 수 급변 상세 API - 오전/오후 구분 비교"""
    date_str = request.GET.get('date')
    product_line = request.GET.get('type', 'tv')

    if date_str:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    else:
        target_date = (datetime.now() - timedelta(days=1)).date()

    prev_date = target_date - timedelta(days=1)

    try:
        conn = get_dx_connection()
        cursor = conn.cursor()

        changes = []

        if product_line == 'tv':
            # TV 리뷰 수 - 오전/오후 구분 비교
            cursor.execute("""
                WITH today_am AS (
                    SELECT item, account_name, retailer_sku_name as product_name,
                           CAST(REPLACE(count_of_star_ratings, ',', '') AS INTEGER) as review_count,
                           product_url, 'AM' as period
                    FROM tv_retail_com
                    WHERE DATE(crawl_datetime::timestamp) = %s
                    AND EXTRACT(HOUR FROM crawl_datetime::timestamp) < 12
                    AND count_of_star_ratings IS NOT NULL
                    AND count_of_star_ratings ~ '^[0-9,]+$'
                ),
                today_pm AS (
                    SELECT item, account_name, retailer_sku_name as product_name,
                           CAST(REPLACE(count_of_star_ratings, ',', '') AS INTEGER) as review_count,
                           product_url, 'PM' as period
                    FROM tv_retail_com
                    WHERE DATE(crawl_datetime::timestamp) = %s
                    AND EXTRACT(HOUR FROM crawl_datetime::timestamp) >= 12
                    AND count_of_star_ratings IS NOT NULL
                    AND count_of_star_ratings ~ '^[0-9,]+$'
                ),
                yesterday_pm AS (
                    SELECT item, account_name,
                           CAST(REPLACE(count_of_star_ratings, ',', '') AS INTEGER) as review_count
                    FROM tv_retail_com
                    WHERE DATE(crawl_datetime::timestamp) = %s
                    AND EXTRACT(HOUR FROM crawl_datetime::timestamp) >= 12
                    AND count_of_star_ratings IS NOT NULL
                    AND count_of_star_ratings ~ '^[0-9,]+$'
                ),
                am_changes AS (
                    SELECT t.item, t.account_name, t.product_name,
                           y.review_count as prev_count, t.review_count as curr_count,
                           ROUND(((t.review_count - y.review_count)::float / y.review_count * 100)::numeric, 2) as change_pct,
                           t.product_url, t.period,
                           (t.review_count - y.review_count)::float / y.review_count as abs_change
                    FROM today_am t
                    JOIN yesterday_pm y ON t.item = y.item AND t.account_name = y.account_name
                    WHERE y.review_count > 0
                    AND (t.review_count - y.review_count)::float / y.review_count > 0.5
                    AND (t.review_count - y.review_count) >= 30
                ),
                pm_changes AS (
                    SELECT t.item, t.account_name, t.product_name,
                           a.review_count as prev_count, t.review_count as curr_count,
                           ROUND(((t.review_count - a.review_count)::float / a.review_count * 100)::numeric, 2) as change_pct,
                           t.product_url, t.period,
                           (t.review_count - a.review_count)::float / a.review_count as abs_change
                    FROM today_pm t
                    JOIN today_am a ON t.item = a.item AND t.account_name = a.account_name
                    WHERE a.review_count > 0
                    AND (t.review_count - a.review_count)::float / a.review_count > 0.5
                    AND (t.review_count - a.review_count) >= 30
                )
                SELECT item, account_name, product_name, prev_count, curr_count, change_pct, product_url, period
                FROM (
                    SELECT * FROM am_changes
                    UNION ALL
                    SELECT * FROM pm_changes
                ) combined
                ORDER BY abs_change DESC
            """, (target_date, target_date, prev_date))
        else:  # hhp
            # HHP 리뷰 수 - 오전/오후 구분 비교
            cursor.execute("""
                WITH today_am AS (
                    SELECT item, account_name, retailer_sku_name as product_name,
                           CAST(REPLACE(count_of_star_ratings, ',', '') AS INTEGER) as review_count,
                           product_url, 'AM' as period
                    FROM hhp_retail_com
                    WHERE DATE(crawl_strdatetime) = %s
                    AND EXTRACT(HOUR FROM crawl_strdatetime::timestamp) < 12
                    AND count_of_star_ratings IS NOT NULL
                    AND count_of_star_ratings ~ '^[0-9,]+$'
                ),
                today_pm AS (
                    SELECT item, account_name, retailer_sku_name as product_name,
                           CAST(REPLACE(count_of_star_ratings, ',', '') AS INTEGER) as review_count,
                           product_url, 'PM' as period
                    FROM hhp_retail_com
                    WHERE DATE(crawl_strdatetime) = %s
                    AND EXTRACT(HOUR FROM crawl_strdatetime::timestamp) >= 12
                    AND count_of_star_ratings IS NOT NULL
                    AND count_of_star_ratings ~ '^[0-9,]+$'
                ),
                yesterday_pm AS (
                    SELECT item, account_name,
                           CAST(REPLACE(count_of_star_ratings, ',', '') AS INTEGER) as review_count
                    FROM hhp_retail_com
                    WHERE DATE(crawl_strdatetime) = %s
                    AND EXTRACT(HOUR FROM crawl_strdatetime::timestamp) >= 12
                    AND count_of_star_ratings IS NOT NULL
                    AND count_of_star_ratings ~ '^[0-9,]+$'
                ),
                am_changes AS (
                    SELECT t.item, t.account_name, t.product_name,
                           y.review_count as prev_count, t.review_count as curr_count,
                           ROUND(((t.review_count - y.review_count)::float / y.review_count * 100)::numeric, 2) as change_pct,
                           t.product_url, t.period,
                           (t.review_count - y.review_count)::float / y.review_count as abs_change
                    FROM today_am t
                    JOIN yesterday_pm y ON t.item = y.item AND t.account_name = y.account_name
                    WHERE y.review_count > 0
                    AND (t.review_count - y.review_count)::float / y.review_count > 0.5
                    AND (t.review_count - y.review_count) >= 30
                ),
                pm_changes AS (
                    SELECT t.item, t.account_name, t.product_name,
                           a.review_count as prev_count, t.review_count as curr_count,
                           ROUND(((t.review_count - a.review_count)::float / a.review_count * 100)::numeric, 2) as change_pct,
                           t.product_url, t.period,
                           (t.review_count - a.review_count)::float / a.review_count as abs_change
                    FROM today_pm t
                    JOIN today_am a ON t.item = a.item AND t.account_name = a.account_name
                    WHERE a.review_count > 0
                    AND (t.review_count - a.review_count)::float / a.review_count > 0.5
                    AND (t.review_count - a.review_count) >= 30
                )
                SELECT item, account_name, product_name, prev_count, curr_count, change_pct, product_url, period
                FROM (
                    SELECT * FROM am_changes
                    UNION ALL
                    SELECT * FROM pm_changes
                ) combined
                ORDER BY abs_change DESC
            """, (target_date, target_date, prev_date))

        rows = cursor.fetchall()
        for row in rows:
            changes.append({
                'item': row[0],
                'account_name': row[1],
                'product_name': str(row[2])[:50] + '...' if row[2] and len(str(row[2])) > 50 else row[2],
                'prev_count': row[3],
                'curr_count': row[4],
                'change_pct': float(row[5]) if row[5] else None,
                'product_url': row[6],
                'period': row[7]  # AM/PM
            })

        cursor.close()
        conn.close()

        return JsonResponse({
            'date': str(target_date),
            'compare_date': str(prev_date),
            'product_line': product_line.upper(),
            'check_type': 'review',
            'threshold': '+50%',
            'total_changes': len(changes),
            'changes': changes
        })

    except Exception as e:
        return safe_error(e)


def price_anomalies(request):
    """가격 이상치 상세 조회 API"""
    date_str = request.GET.get('date')
    product_line = request.GET.get('type', 'tv')

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
                    product_name,
                    account_name,
                    final_sku_price,
                    main_rank,
                    crawl_datetime
                FROM tv_retail_com
                WHERE DATE(crawl_datetime::timestamp) = %s
                AND (final_sku_price < 0 OR final_sku_price > 50000)
                ORDER BY final_sku_price DESC
            """, (target_date,))
        else:
            cursor.execute("""
                SELECT
                    product_name,
                    account_name,
                    final_sku_price,
                    main_rank,
                    crawl_strdatetime
                FROM hhp_retail_com
                WHERE DATE(crawl_strdatetime) = %s
                AND (final_sku_price < 0 OR final_sku_price > 5000)
                ORDER BY final_sku_price DESC
            """, (target_date,))

        rows = cursor.fetchall()
        anomalies = []
        for row in rows:
            anomalies.append({
                'product_name': row[0],
                'retailer': row[1],
                'price': float(row[2]) if row[2] else None,
                'rank': row[3],
                'timestamp': str(row[4]) if row[4] else None
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
        return safe_error(e)


def price_changes(request):
    """급격한 가격 변동 조회 API"""
    date_str = request.GET.get('date')
    product_line = request.GET.get('type', 'tv')
    threshold = float(request.GET.get('threshold', 0.3))

    if date_str:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    else:
        target_date = (datetime.now() - timedelta(days=1)).date()

    prev_date = target_date - timedelta(days=1)

    try:
        conn = get_dx_connection()
        cursor = conn.cursor()

        if product_line == 'tv':
            cursor.execute("""
                WITH today AS (
                    SELECT item, product_name, account_name, final_sku_price as price, product_url
                    FROM tv_retail_com
                    WHERE DATE(crawl_datetime::timestamp) = %s
                    AND final_sku_price IS NOT NULL
                ),
                yesterday AS (
                    SELECT item, product_name, account_name, final_sku_price as price
                    FROM tv_retail_com
                    WHERE DATE(crawl_datetime::timestamp) = %s
                    AND final_sku_price IS NOT NULL
                )
                SELECT
                    t.item,
                    t.account_name,
                    t.product_name,
                    y.price as prev_price,
                    t.price as curr_price,
                    ROUND(((t.price - y.price) / NULLIF(y.price, 0) * 100)::numeric, 2) as change_pct,
                    t.product_url
                FROM today t
                JOIN yesterday y ON t.item = y.item AND t.account_name = y.account_name
                WHERE ABS(t.price - y.price) / NULLIF(y.price, 0) > %s
                ORDER BY ABS(t.price - y.price) / NULLIF(y.price, 0) DESC
            """, (target_date, prev_date, threshold))
        else:
            cursor.execute("""
                WITH today AS (
                    SELECT item, product_name, account_name,
                           CAST(REPLACE(REPLACE(SPLIT_PART(REPLACE(final_sku_price, '$', ''), '/', 1), ',', ''), ' ', '') AS NUMERIC) as price,
                           product_url
                    FROM hhp_retail_com
                    WHERE DATE(crawl_strdatetime) = %s
                    AND final_sku_price IS NOT NULL
                    AND final_sku_price LIKE '$%%'
                ),
                yesterday AS (
                    SELECT item, product_name, account_name,
                           CAST(REPLACE(REPLACE(SPLIT_PART(REPLACE(final_sku_price, '$', ''), '/', 1), ',', ''), ' ', '') AS NUMERIC) as price
                    FROM hhp_retail_com
                    WHERE DATE(crawl_strdatetime) = %s
                    AND final_sku_price IS NOT NULL
                    AND final_sku_price LIKE '$%%'
                )
                SELECT
                    t.item,
                    t.account_name,
                    t.product_name,
                    y.price as prev_price,
                    t.price as curr_price,
                    ROUND(((t.price - y.price) / NULLIF(y.price, 0) * 100)::numeric, 2) as change_pct,
                    t.product_url
                FROM today t
                JOIN yesterday y ON t.item = y.item AND t.account_name = y.account_name
                WHERE t.price > 0 AND y.price > 0
                AND ABS(t.price - y.price) / NULLIF(y.price, 0) > %s
                ORDER BY ABS(t.price - y.price) / NULLIF(y.price, 0) DESC
            """, (target_date, prev_date, threshold))

        rows = cursor.fetchall()
        changes = []
        for row in rows:
            changes.append({
                'item': row[0],
                'retailer': row[1],
                'product_name': row[2],
                'prev_price': float(row[3]) if row[3] else None,
                'curr_price': float(row[4]) if row[4] else None,
                'change_pct': float(row[5]) if row[5] else None,
                'product_url': row[6]
            })

        cursor.close()
        conn.close()

        return JsonResponse({
            'date': str(target_date),
            'prev_date': str(prev_date),
            'product_line': product_line.upper(),
            'threshold': f'{threshold * 100}%',
            'total_changes': len(changes),
            'changes': changes
        })

    except Exception as e:
        return safe_error(e)


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
                _validate_table_name(table_name)
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
                        non_products = _get_non_product_set(cursor, table_name, rule.get('product_line'), pairs)
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
        _validate_table_name(table_name)
        date_col = (target_rule.get('date_column') or '').strip()
        has_date_filter = bool(date_col)

        # 쿼리 가져와서 실행
        query_template = target_rule.get('query', '')
        if query_template:
            query = query_template.replace('{table}', table_name).replace('{date_col}', date_col)
            if not _validate_select_query(query):
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
            mst_table = _validate_table_name('hhp_item_mst' if 'hhp' in product_line_val or 'hhp' in table_name else 'tv_item_mst')
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


def field_missing_detection(request):
    """
    필드 누락 탐지 API
    - 직전 2일 vs 오늘 비교
    - 직전에는 값이 있었는데 오늘 NULL/빈값인 필드 탐지
    """
    import csv
    import os

    date_str = request.GET.get('date')
    product_line = request.GET.get('type', 'tv')  # tv, hhp
    retailer = request.GET.get('retailer', 'all')  # Amazon, Bestbuy, Walmart, all

    if date_str:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    else:
        target_date = (datetime.now() - timedelta(days=1)).date()

    # 직전 2일
    prev_date_1 = target_date - timedelta(days=1)
    prev_date_2 = target_date - timedelta(days=2)

    # DB에서 리테일러별 수집 필드 로드 (skip_missing_check=TRUE인 필드 제외)
    from apps.common.retail_columns import get_retail_columns_for_retailer, get_missing_exclude_conditions
    retail_columns = {}

    for ret in ['Amazon', 'Bestbuy', 'Walmart']:
        cols = get_retail_columns_for_retailer(product_line, ret)
        if cols:
            retail_columns[ret] = cols

    try:
        conn = get_dx_connection()
        cursor = conn.cursor()

        results = {
            'date': str(target_date),
            'product_line': product_line.upper(),
            'retailer': retailer,
            'prev_dates': [str(prev_date_1), str(prev_date_2)],
            'summary': {},
            'missing_fields': []
        }

        # 테이블명과 날짜 컬럼 결정
        if product_line == 'tv':
            table_name = 'tv_retail_com'
            date_column = 'crawl_datetime::timestamp'
        else:
            table_name = 'hhp_retail_com'
            date_column = 'crawl_strdatetime'

        # 리테일러 목록
        retailers_to_check = ['Amazon', 'Bestbuy', 'Walmart'] if retailer == 'all' else [retailer]

        total_missing = 0

        for ret in retailers_to_check:
            if ret not in retail_columns:
                continue

            columns_to_check = retail_columns[ret]
            # 기본 필드 제외 (항상 있어야 하는 필드)
            exclude_cols = ['id', 'item', 'account_name', 'page_type', 'crawl_datetime', 'crawl_strdatetime', 'calendar_week']
            columns_to_check = [c for c in columns_to_check if c not in exclude_cols]

            if not columns_to_check:
                continue

            # 모든 필드에 대해 한번의 쿼리로 처리
            # 각 필드별로 직전값 존재 여부, 오늘 NULL 여부를 item별로 집계
            case_prev = []
            case_today = []
            for col in columns_to_check:
                safe_col = f'"{col}"'
                case_prev.append(f"MAX(CASE WHEN DATE({date_column}) IN ('{prev_date_1}', '{prev_date_2}') AND {safe_col} IS NOT NULL AND CAST({safe_col} AS TEXT) != '' THEN 1 ELSE 0 END) as prev_{col.replace(' ', '_')}")

                # exclude 조건 적용
                exclude_conds = get_missing_exclude_conditions(ret, table_name, col)
                exclude_conds = [c for c in exclude_conds if _validate_exclude_condition(c)]
                exclude_sql = ""
                if exclude_conds:
                    # psycopg2에서 %를 %%로 이스케이프 (LIKE 패턴 등)
                    exclude_parts = " OR ".join([f"({c.replace('%', '%%')})" for c in exclude_conds])
                    exclude_sql = f" AND NOT ({exclude_parts})"

                case_today.append(f"MAX(CASE WHEN DATE({date_column}) = '{target_date}' AND ({safe_col} IS NULL OR CAST({safe_col} AS TEXT) = ''){exclude_sql} THEN 1 ELSE 0 END) as today_{col.replace(' ', '_')}")

            query = f"""
                SELECT item, {', '.join(case_prev)}, {', '.join(case_today)}
                FROM {table_name}
                WHERE account_name = %s
                AND DATE({date_column}) IN (%s, %s, %s)
                GROUP BY item
            """
            cursor.execute(query, (ret, prev_date_1, prev_date_2, target_date))
            rows = cursor.fetchall()

            # 각 필드별 누락 카운트 계산
            field_stats = {col: {'prev_count': 0, 'missing_count': 0, 'missing_items': []} for col in columns_to_check}
            num_cols = len(columns_to_check)

            for row in rows:
                # row: (item, prev_col1, prev_col2, ..., today_col1, today_col2, ...)
                item_name = row[0]
                for i, col in enumerate(columns_to_check):
                    prev_val = row[1 + i]  # prev 값들
                    today_val = row[1 + num_cols + i]  # today 값들
                    if prev_val == 1:
                        field_stats[col]['prev_count'] += 1
                        if today_val == 1:
                            field_stats[col]['missing_count'] += 1
                            field_stats[col]['missing_items'].append(item_name)

            # 각 필드별 오늘 날짜 누락 데이터 수(행 수) 조회
            for col in columns_to_check:
                stats = field_stats[col]
                if stats['missing_count'] > 0 and stats['missing_items']:
                    # 누락 item들의 오늘 날짜 NULL 행 수 조회
                    safe_col = f'"{col}"'
                    placeholders = ', '.join(['%s'] * len(stats['missing_items']))
                    # exclude 조건 적용
                    exclude_conds = get_missing_exclude_conditions(ret, table_name, col)
                    exclude_conds = [c for c in exclude_conds if _validate_exclude_condition(c)]
                    exclude_sql = ""
                    if exclude_conds:
                        exclude_parts = " OR ".join([f"({c.replace('%', '%%')})" for c in exclude_conds])
                        exclude_sql = f" AND NOT ({exclude_parts})"

                    null_count_query = f"""
                        SELECT COUNT(*) FROM {table_name}
                        WHERE account_name = %s
                        AND DATE({date_column}) = %s
                        AND item IN ({placeholders})
                        AND ({safe_col} IS NULL OR CAST({safe_col} AS TEXT) = ''){exclude_sql}
                    """
                    cursor.execute(null_count_query, (ret, target_date, *stats['missing_items']))
                    stats['today_null_rows'] = cursor.fetchone()[0] or 0

            # 결과 집계
            for col in columns_to_check:
                stats = field_stats[col]
                if stats['missing_count'] > 0:
                    total_missing += stats['missing_count']
                    results['missing_fields'].append({
                        'retailer': ret,
                        'column': col,
                        'prev_had_value_items': stats['prev_count'],
                        'today_missing_items': stats['missing_count'],
                        'today_null_rows': stats.get('today_null_rows', 0),  # 누락 데이터 수 (행 수)
                        'missing_rate': round(stats['missing_count'] / stats['prev_count'] * 100, 2) if stats['prev_count'] > 0 else 0
                    })

        results['summary'] = {
            'total_missing_cases': total_missing,
            'fields_with_issues': len(results['missing_fields']),
            'status': 'OK' if total_missing == 0 else ('WARNING' if total_missing < 10 else 'CRITICAL')
        }

        cursor.close()
        conn.close()

        return JsonResponse(results)

    except Exception as e:
        log_error(e)
        return safe_error(e)


def field_missing_detail_all(request):
    """
    필드 누락 탐지 상세 - 3일치 raw 데이터 (무한스크롤용)
    item + crawl_datetime 순으로 정렬, 필드들을 컬럼으로 표시
    offset/limit 파라미터로 데이터 분할 조회
    """
    import csv
    import os

    date_str = request.GET.get('date')
    product_line = request.GET.get('product_line', request.GET.get('type', 'tv'))
    retailer = request.GET.get('retailer', 'Amazon')
    try:
        offset = max(0, int(request.GET.get('offset', 0)))
        limit = min(int(request.GET.get('limit', 100)), 500)
    except (ValueError, TypeError):
        offset = 0
        limit = 100

    if date_str:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    else:
        target_date = (datetime.now() - timedelta(days=1)).date()

    prev_date_1 = target_date - timedelta(days=1)
    prev_date_2 = target_date - timedelta(days=2)

    # DB에서 리테일러별 수집 필드 로드
    from apps.common.retail_columns import get_retailer_columns
    retail_columns = get_retailer_columns(product_line, retailer)

    # 표시할 필드 선택 (긴 텍스트 필드 제외)
    exclude_cols = ['calendar_week', 'detailed_review_content', 'summarized_review_content']
    display_fields = [c for c in retail_columns if c not in exclude_cols and c not in ['id', 'item', 'account_name', 'page_type', 'crawl_datetime', 'crawl_strdatetime', 'product_url']]

    try:
        conn = get_dx_connection()
        cursor = conn.cursor()

        if product_line == 'tv':
            table_name = 'tv_retail_com'
            date_column = 'crawl_datetime'
            date_cast = 'crawl_datetime::timestamp'
        else:
            table_name = 'hhp_retail_com'
            date_column = 'crawl_strdatetime'
            date_cast = 'crawl_strdatetime'

        # SELECT 절 구성: id, crawl_datetime, item + 표시 필드들 + product_url(마지막)
        select_cols = ['id', date_column, 'item']
        for col in display_fields:
            select_cols.append(f'"{col}"')
        select_cols.append('product_url')  # URL은 마지막에

        select_clause = ', '.join(select_cols)

        # 먼저 총 건수 조회 (첫 요청시에만)
        total_count = 0
        if offset == 0:
            cursor.execute(f"""
                SELECT COUNT(*)
                FROM {table_name}
                WHERE account_name = %s
                AND DATE({date_cast}) IN (%s, %s, %s)
            """, (retailer, prev_date_2, prev_date_1, target_date))
            total_count = cursor.fetchone()[0]

        # 3일치 데이터 조회 (item, crawl_datetime 순 정렬, 무한스크롤용)
        cursor.execute(f"""
            SELECT {select_clause}
            FROM {table_name}
            WHERE account_name = %s
            AND DATE({date_cast}) IN (%s, %s, %s)
            ORDER BY item, {date_column} ASC
            LIMIT %s OFFSET %s
        """, (retailer, prev_date_2, prev_date_1, target_date, limit, offset))

        rows = cursor.fetchall()

        # 컬럼명 목록 (product_url은 마지막)
        column_names = ['id', date_column, 'item'] + display_fields + ['product_url']

        # 데이터 변환
        all_data = []
        for row in rows:
            row_dict = {}
            for i, col_name in enumerate(column_names):
                val = row[i]
                # datetime 변환
                if col_name == date_column and val:
                    val = str(val)
                # 긴 텍스트 자르기 (product_url은 링크 동작을 위해 제외)
                if val and isinstance(val, str) and len(val) > 100 and col_name != 'product_url':
                    val = val[:100] + '...'
                row_dict[col_name] = val
            all_data.append(row_dict)

        cursor.close()
        conn.close()

        response_data = {
            'status': 'success',
            'date': str(target_date),
            'prev_dates': [str(prev_date_2), str(prev_date_1)],
            'product_line': product_line.upper(),
            'retailer': retailer,
            'columns': column_names,
            'display_fields': display_fields,
            'offset': offset,
            'limit': limit,
            'fetched_rows': len(all_data),
            'has_more': len(all_data) == limit,
            'data': all_data
        }

        # 첫 요청시에만 total_count 포함
        if offset == 0:
            response_data['total_count'] = total_count

        return JsonResponse(response_data)

    except Exception as e:
        log_error(e)
        return JsonResponse({'status': 'error', 'message': '처리 중 오류가 발생했습니다.'})


def field_missing_detail_problem(request):
    """
    필드 누락 탐지 상세 - 문제 있는 item만 (직전에 있었는데 오늘 없는)
    column 파라미터 없으면 해당 리테일러의 모든 컬럼 검사
    무한 스크롤: offset, limit 파라미터 지원
    """
    import csv
    import os

    date_str = request.GET.get('date')
    product_line = request.GET.get('product_line', request.GET.get('type', 'tv'))
    retailer = request.GET.get('retailer', 'Amazon')
    column = request.GET.get('column', '')  # 선택: 검사할 컬럼 (없으면 모든 컬럼)
    try:
        offset = max(0, int(request.GET.get('offset', 0)))
        limit = min(int(request.GET.get('limit', 100)), 500)
    except (ValueError, TypeError):
        offset = 0
        limit = 100

    if date_str:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    else:
        target_date = (datetime.now() - timedelta(days=1)).date()

    prev_date_1 = target_date - timedelta(days=1)
    prev_date_2 = target_date - timedelta(days=2)

    # DB에서 리테일러별 수집 필드 로드
    from apps.common.retail_columns import get_retailer_columns
    retail_columns = get_retailer_columns(product_line, retailer)

    # 기본 필드 제외
    exclude_cols = ['id', 'item', 'account_name', 'page_type', 'crawl_datetime', 'crawl_strdatetime', 'calendar_week', 'product_url']
    columns_to_check = [c for c in retail_columns if c not in exclude_cols]

    # column 파라미터가 있으면 해당 컬럼만
    if column:
        columns_to_check = [column] if column in columns_to_check else []

    try:
        conn = get_dx_connection()
        cursor = conn.cursor()

        if product_line == 'tv':
            table_name = 'tv_retail_com'
            date_column = 'crawl_datetime'
            date_cast = 'crawl_datetime::timestamp'
        else:
            table_name = 'hhp_retail_com'
            date_column = 'crawl_strdatetime'
            date_cast = 'crawl_strdatetime'

        # 모든 컬럼에 대한 누락 데이터를 UNION ALL로 한번에 조회
        union_queries = []
        params = []

        for col in columns_to_check:
            safe_col = f'"{col}"'
            union_queries.append(f"""
                SELECT
                    p.item,
                    p.account_name,
                    '{col}' as field_name,
                    p.prev_value
                FROM (
                    SELECT DISTINCT item, account_name, MAX(CAST({safe_col} AS TEXT)) as prev_value
                    FROM {table_name}
                    WHERE account_name = %s
                    AND DATE({date_cast}) IN (%s, %s)
                    AND {safe_col} IS NOT NULL
                    AND CAST({safe_col} AS TEXT) != ''
                    GROUP BY item, account_name
                ) p
                LEFT JOIN (
                    SELECT DISTINCT item, account_name, {safe_col}
                    FROM {table_name}
                    WHERE account_name = %s
                    AND DATE({date_cast}) = %s
                ) t ON p.item = t.item AND p.account_name = t.account_name
                WHERE t.{safe_col} IS NULL OR CAST(t.{safe_col} AS TEXT) = ''
            """)
            params.extend([retailer, prev_date_1, prev_date_2, retailer, target_date])

        if not union_queries:
            cursor.close()
            conn.close()
            return JsonResponse({
                'status': 'success',
                'date': str(target_date),
                'prev_dates': [str(prev_date_1), str(prev_date_2)],
                'product_line': product_line.upper(),
                'retailer': retailer,
                'fields': columns_to_check,
                'total_count': 0,
                'offset': offset,
                'limit': limit,
                'has_more': False,
                'data': []
            })

        full_query = " UNION ALL ".join(union_queries)

        # 먼저 전체 카운트 조회
        count_query = f"SELECT COUNT(*) FROM ({full_query}) as all_data"
        cursor.execute(count_query, params)
        total_count = cursor.fetchone()[0]

        # 페이지네이션 적용한 데이터 조회
        data_query = f"""
            SELECT * FROM ({full_query}) as all_data
            ORDER BY field_name, item
            OFFSET %s LIMIT %s
        """
        cursor.execute(data_query, params + [offset, limit])

        rows = cursor.fetchall()
        all_missing = []
        for row in rows:
            prev_val = row[3]
            all_missing.append({
                'item': row[0],
                'account_name': row[1],
                'field_name': row[2],
                'd2_value': prev_val[:100] if prev_val and len(prev_val) > 100 else prev_val,
                'd1_value': prev_val[:100] if prev_val and len(prev_val) > 100 else prev_val,
                'today_value': None,
                'today_has_value': False
            })

        cursor.close()
        conn.close()

        return JsonResponse({
            'status': 'success',
            'date': str(target_date),
            'prev_dates': [str(prev_date_1), str(prev_date_2)],
            'product_line': product_line.upper(),
            'retailer': retailer,
            'fields': columns_to_check,
            'total_count': total_count,
            'offset': offset,
            'limit': limit,
            'has_more': (offset + limit) < total_count,
            'data': all_missing
        })

    except Exception as e:
        log_error(e)
        return JsonResponse({'status': 'error', 'message': '처리 중 오류가 발생했습니다.'})


def field_missing_detail_by_field(request):
    """
    특정 필드의 누락 item들에 대한 3일치 raw 데이터 조회
    - 직전 2일에 값이 있었는데 오늘 없는 item들의 3일치 전체 데이터
    """
    import csv
    import os

    date_str = request.GET.get('date')
    product_line = request.GET.get('product_line', 'tv')
    retailer = request.GET.get('retailer', 'Amazon')
    field = request.GET.get('field', '')  # 필수: 조회할 필드

    if not field:
        return JsonResponse({'status': 'error', 'message': 'field 파라미터가 필요합니다.'})

    if date_str:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    else:
        target_date = (datetime.now() - timedelta(days=1)).date()

    prev_date_1 = target_date - timedelta(days=1)
    prev_date_2 = target_date - timedelta(days=2)

    # DB에서 리테일러별 수집 필드 및 related_columns 로드
    from apps.common.retail_columns import get_retail_columns_with_related, get_missing_exclude_conditions as get_exclude_conds
    columns_info = get_retail_columns_with_related(product_line, retailer)
    display_fields = [c['column_name'] for c in columns_info]
    related_columns = []
    for c in columns_info:
        if c['column_name'] == field and c['related_columns']:
            related_columns = [col.strip() for col in c['related_columns'].split('|') if col.strip()]
            break

    if field not in display_fields:
        return JsonResponse({'status': 'error', 'message': '허용되지 않은 필드'})

    try:
        conn = get_dx_connection()
        cursor = conn.cursor()

        if product_line == 'tv':
            table_name = 'tv_retail_com'
            date_column = 'crawl_datetime'
            date_cast = 'crawl_datetime::timestamp'
        else:
            table_name = 'hhp_retail_com'
            date_column = 'crawl_strdatetime'
            date_cast = 'crawl_strdatetime'

        safe_field = f'"{field}"'

        # SELECT 컬럼 구성: 필수(id, 수집시간, item) + 조회용 컬럼 or 누락필드 + URL(마지막)
        # 조회용 컬럼이 있으면 조회용 컬럼만, 없으면 누락필드만 표시
        select_cols = ['id', date_column, 'item']
        if related_columns:
            for rel_col in related_columns:
                if rel_col in display_fields:
                    select_cols.append(f'"{rel_col}"')
        else:
            select_cols.append(safe_field)
        select_cols.append('product_url')  # URL은 마지막에
        select_clause = ', '.join(select_cols)

        # 먼저 요약 API와 동일한 방식으로 누락 item 목록 추출
        # (직전 2일에 값이 있었고, 오늘 NULL인 item)
        # exclude 조건 적용 (요약과 동일)
        exclude_conds = get_exclude_conds(retailer, table_name, field)
        exclude_conds = [c for c in exclude_conds if _validate_exclude_condition(c)]
        exclude_sql = ""
        if exclude_conds:
            exclude_parts = " OR ".join([f"({c.replace('%', '%%')})" for c in exclude_conds])
            exclude_sql = f" AND NOT ({exclude_parts})"

        missing_items_query = f"""
            SELECT item
            FROM {table_name}
            WHERE account_name = %s
            AND DATE({date_cast}) IN (%s, %s, %s)
            GROUP BY item
            HAVING
                MAX(CASE WHEN DATE({date_cast}) IN (%s, %s) AND {safe_field} IS NOT NULL AND CAST({safe_field} AS TEXT) != '' THEN 1 ELSE 0 END) = 1
                AND MAX(CASE WHEN DATE({date_cast}) = %s AND ({safe_field} IS NULL OR CAST({safe_field} AS TEXT) = ''){exclude_sql} THEN 1 ELSE 0 END) = 1
        """

        cursor.execute(missing_items_query, (
            retailer, prev_date_2, prev_date_1, target_date,
            prev_date_1, prev_date_2,
            target_date
        ))
        missing_items = [row[0] for row in cursor.fetchall()]

        if not missing_items:
            # 누락 item이 없으면 빈 결과 반환
            # 컬럼명 목록 생성 (select_cols와 동일한 순서)
            column_names = ['id', date_column, 'item']
            if related_columns:
                for rel_col in related_columns:
                    if rel_col in display_fields:
                        column_names.append(rel_col)
            else:
                column_names.append(field)
            column_names.append('product_url')

            cursor.close()
            conn.close()
            return JsonResponse({
                'status': 'success',
                'date': str(target_date),
                'prev_dates': [str(prev_date_2), str(prev_date_1)],
                'product_line': product_line.upper(),
                'retailer': retailer,
                'field': field,
                'columns': column_names,
                'total_rows': 0,
                'data': []
            })

        # 누락 item들의 3일치 데이터 조회
        placeholders = ', '.join(['%s'] * len(missing_items))
        query = f"""
            SELECT {select_clause}
            FROM {table_name}
            WHERE account_name = %s
            AND DATE({date_cast}) IN (%s, %s, %s)
            AND item IN ({placeholders})
            ORDER BY item, {date_column}
        """

        cursor.execute(query, (
            retailer, prev_date_2, prev_date_1, target_date,
            *missing_items
        ))

        rows = cursor.fetchall()

        # 컬럼명 목록: select_cols와 동일한 순서
        column_names = ['id', date_column, 'item']
        if related_columns:
            for rel_col in related_columns:
                if rel_col in display_fields:
                    column_names.append(rel_col)
        else:
            column_names.append(field)
        column_names.append('product_url')

        # 데이터 변환
        all_data = []
        today_null_count = 0  # 오늘 날짜의 NULL 행 수
        for row in rows:
            row_dict = {}
            for i, col_name in enumerate(column_names):
                val = row[i]
                if col_name == date_column and val:
                    val = str(val)
                # product_url은 자르지 않음 (링크 동작 필요)
                if val and isinstance(val, str) and len(val) > 100 and col_name != 'product_url':
                    val = val[:100] + '...'
                row_dict[col_name] = val
            all_data.append(row_dict)

            # 오늘 날짜이고 해당 필드가 NULL인 경우 카운트
            crawl_date = row_dict.get(date_column, '')[:10] if row_dict.get(date_column) else ''
            field_val = row_dict.get(field)
            if crawl_date == str(target_date) and (field_val is None or field_val == ''):
                today_null_count += 1

        cursor.close()
        conn.close()

        return JsonResponse({
            'status': 'success',
            'date': str(target_date),
            'prev_dates': [str(prev_date_2), str(prev_date_1)],
            'product_line': product_line.upper(),
            'retailer': retailer,
            'field': field,
            'columns': column_names,
            'total_rows': len(all_data),
            'missing_item_count': len(missing_items),  # 누락 item 수
            'today_null_count': today_null_count,  # 오늘 날짜의 누락 데이터 수
            'data': all_data
        })

    except Exception as e:
        log_error(e)
        return JsonResponse({'status': 'error', 'message': '처리 중 오류가 발생했습니다.'})


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


