"""
DX 컬럼 설정 로드
CSV 파일에서 TV/HHP 리테일러별 컬럼 정보 및 NULL 체크 컬럼 정보를 읽어옴
"""

import csv
from pathlib import Path

# CSV 파일 경로 (config/csv 폴더)
CSV_DIR = Path(__file__).parent.parent.parent / 'config' / 'csv'
RETAIL_COLUMNS_CSV_PATH = CSV_DIR / 'dx_retail_columns.csv'
NULL_CHECK_CSV_PATH = CSV_DIR / 'dx_null_check.csv'

# 캐시된 데이터
_retail_columns_cache = None
_null_check_config_cache = None


def load_retail_columns():
    """
    dx_retail_columns.csv에서 리테일러별 컬럼 정보 로드
    CSV 구조: product_line, column_name, Amazon, Bestbuy, Walmart
    Y 표시된 컬럼은 해당 리테일러에 포함되며 자동으로 NULL 체크 대상

    Returns: {
        'tv': {
            'Amazon': [column1, column2, ...],
            'Bestbuy': [...],
            'Walmart': [...]
        },
        'hhp': {...}
    }
    """
    global _retail_columns_cache
    if _retail_columns_cache is not None:
        return _retail_columns_cache

    result = {
        'tv': {'Amazon': [], 'Bestbuy': [], 'Walmart': []},
        'hhp': {'Amazon': [], 'Bestbuy': [], 'Walmart': []}
    }

    try:
        with open(RETAIL_COLUMNS_CSV_PATH, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                product_line = row['product_line'].lower()
                column_name = row['column_name']

                # 각 리테일러별로 Y 표시된 컬럼만 추가
                for retailer in ['Amazon', 'Bestbuy', 'Walmart']:
                    if row.get(retailer, '').upper() == 'Y':
                        result[product_line][retailer].append(column_name)

        _retail_columns_cache = result
        print(f"[INFO] Retail columns loaded from CSV: TV retailers={list(result['tv'].keys())}, HHP retailers={list(result['hhp'].keys())}")
    except Exception as e:
        print(f"[ERROR] Failed to load retail columns CSV: {e}")

    return result


def get_retailer_columns(product_line, retailer):
    """
    특정 리테일러의 컬럼 목록 반환 (Y 표시된 컬럼 = NULL 체크 대상)

    Args:
        product_line: 'tv' 또는 'hhp'
        retailer: 'Amazon', 'Bestbuy', 'Walmart'

    Returns:
        list: 컬럼명 리스트
    """
    columns_data = load_retail_columns()
    product_key = product_line.lower()

    if product_key not in columns_data:
        return []

    return columns_data[product_key].get(retailer, [])


def get_all_retailer_columns(product_line):
    """
    해당 제품라인의 모든 리테일러 컬럼 정보 반환

    Args:
        product_line: 'tv' 또는 'hhp'

    Returns:
        dict: {retailer: [columns...], ...}
    """
    columns_data = load_retail_columns()
    product_key = product_line.lower()

    if product_key not in columns_data:
        return {}

    return columns_data[product_key]


def reload_retail_columns():
    """캐시 초기화 후 다시 로드 (CSV 수정 시 사용)"""
    global _retail_columns_cache
    _retail_columns_cache = None
    return load_retail_columns()


def get_retailer_list():
    """
    CSV에서 리테일러 목록 반환 (헤더에서 추출)

    Returns:
        list: ['Amazon', 'Bestbuy', 'Walmart']
    """
    try:
        with open(RETAIL_COLUMNS_CSV_PATH, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            # 헤더에서 product_line, column_name, duplicate_key 제외한 컬럼이 리테일러
            headers = reader.fieldnames or []
            excluded = ['product_line', 'column_name', 'duplicate_key', 'skip_missing_check']
            return [h for h in headers if h not in excluded]
    except Exception as e:
        print(f"[ERROR] Failed to get retailer list: {e}")
        return ['Amazon', 'Bestbuy', 'Walmart']  # 기본값


def get_retail_duplicate_keys(product_line):
    """
    특정 제품라인(tv/hhp)의 중복검증 키 컬럼 목록 반환 (duplicate_key=Y인 컬럼)

    Args:
        product_line: 'tv' 또는 'hhp'

    Returns:
        list: ['item', 'account_name'] 등 중복키 컬럼 목록
    """
    try:
        with open(RETAIL_COLUMNS_CSV_PATH, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            duplicate_keys = []
            for row in reader:
                if row['product_line'].lower() == product_line.lower():
                    if row.get('duplicate_key', 'N').upper() == 'Y':
                        duplicate_keys.append(row['column_name'])
            return duplicate_keys
    except Exception as e:
        print(f"[ERROR] Failed to get retail duplicate keys: {e}")
        return ['item', 'account_name']  # 기본값


# ============================================================
# NULL 검증 설정 관련 함수 (dx_null_check.csv)
# category -> check_name -> columns 계층 구조로 관리
# ============================================================

def load_null_check_config():
    """
    dx_null_check.csv에서 NULL 검증 설정 로드
    CSV 구조: category, check_name, table_name, check_column, check_type, date_column, display_columns, query_columns
    - category: 대시보드 테이블 그룹 (예: tv_retail, hhp_retail, youtube, market)
    - check_name: 검증 카테고리 (예: amazon_tv, youtube_logs, market_trend)
    - table_name: 테이블명 (예: tv_retail_com)
    - check_column: NULL 검증 대상 컬럼 (예: screen_size)
    - check_type: null, empty, both (null만, 공백만, 둘다)
    - date_column: 날짜 컬럼 (예: crawl_datetime)
    - display_columns: 상세보기 표시 컬럼 (파이프 구분)
    - query_columns: 복사 쿼리에 포함할 컬럼 (파이프 구분)

    Returns: {
        'amazon_tv': {
            'category': 'tv_retail',
            'table_name': 'tv_retail_com',
            'date_column': 'crawl_datetime',
            'columns': {
                'item': {'check_type': 'both', 'display_columns': [...], 'query_columns': [...]},
                'screen_size': {...},
                ...
            }
        },
        'youtube_logs': {...},
        ...
    }
    """
    global _null_check_config_cache
    if _null_check_config_cache is not None:
        return _null_check_config_cache

    result = {}

    try:
        with open(NULL_CHECK_CSV_PATH, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                category = row.get('category', '')
                check_name = row['check_name']
                table_name = row['table_name']
                check_column = row['check_column']
                check_type = row.get('check_type', 'both')
                date_column = row.get('date_column', '')
                display_columns = row.get('display_columns', '')
                query_columns = row.get('query_columns', '')
                query_days = int(row.get('query_days', '0') or '0')

                if check_name not in result:
                    result[check_name] = {
                        'category': category,
                        'table_name': table_name,
                        'date_column': date_column,
                        'columns': {}
                    }

                result[check_name]['columns'][check_column] = {
                    'check_type': check_type,
                    'display_columns': [col.strip() for col in display_columns.split('|') if col.strip()],
                    'query_columns': [col.strip() for col in query_columns.split('|') if col.strip()],
                    'query_days': query_days
                }

        _null_check_config_cache = result
        print(f"[INFO] Null check config loaded from CSV: categories={list(result.keys())}")
    except Exception as e:
        print(f"[ERROR] Failed to load null check CSV: {e}")

    return result


def get_null_check_config(check_name, check_column=None):
    """
    특정 카테고리/컬럼의 NULL 검증 설정 반환

    Args:
        check_name: 검증 카테고리 (예: 'amazon_tv', 'youtube_logs')
        check_column: 검증 대상 컬럼 (없으면 카테고리 전체 설정 반환)

    Returns:
        dict: 컬럼 설정 또는 카테고리 전체 설정
    """
    config = load_null_check_config()
    category_config = config.get(check_name)
    if not category_config:
        return None

    if check_column:
        col_config = category_config['columns'].get(check_column)
        if col_config:
            return {
                'table_name': category_config['table_name'],
                'date_column': category_config['date_column'],
                **col_config
            }
        return None
    return category_config


def get_null_check_query_parts(check_name):
    """
    특정 카테고리의 NULL 체크 쿼리 파트 생성 (건수 체크용)

    Args:
        check_name: 검증 카테고리 (예: 'amazon_tv', 'youtube_logs')

    Returns:
        dict: {
            'table_name': 'tv_retail_com',
            'date_column': 'crawl_datetime',
            'count_parts': ['COUNT(CASE WHEN col IS NULL THEN 1 END) as null_col', ...],
            'column_names': ['item', 'screen_size', ...]
        }
        또는 카테고리가 없으면 None
    """
    category_config = get_null_check_config(check_name)
    if not category_config:
        return None

    count_parts = []
    column_names = []

    for col_name, col_config in category_config['columns'].items():
        column_names.append(col_name)
        check_type = col_config.get('check_type', 'both')

        if check_type == 'null':
            count_parts.append(
                f"COUNT(CASE WHEN {col_name} IS NULL THEN 1 END) as null_{col_name}"
            )
        elif check_type == 'empty':
            count_parts.append(
                f"COUNT(CASE WHEN CAST({col_name} AS TEXT) = '' THEN 1 END) as null_{col_name}"
            )
        else:  # both
            count_parts.append(
                f"COUNT(CASE WHEN {col_name} IS NULL OR CAST({col_name} AS TEXT) = '' THEN 1 END) as null_{col_name}"
            )

    return {
        'table_name': category_config['table_name'],
        'date_column': category_config['date_column'],
        'count_parts': count_parts,
        'column_names': column_names
    }


def get_null_detail_query_parts(check_name):
    """
    특정 카테고리의 NULL 상세 조회 쿼리 파트 생성

    Args:
        check_name: 검증 카테고리

    Returns:
        dict: {
            'table_name': 'tv_retail_com',
            'date_column': 'crawl_datetime',
            'where_conditions': ['(item IS NULL OR item = '')', ...],
        }
        또는 카테고리가 없으면 None
    """
    category_config = get_null_check_config(check_name)
    if not category_config:
        return None

    where_conditions = []

    for col_name, col_config in category_config['columns'].items():
        check_type = col_config.get('check_type', 'both')

        if check_type == 'null':
            where_conditions.append(f"{col_name} IS NULL")
        elif check_type == 'empty':
            where_conditions.append(f"CAST({col_name} AS TEXT) = ''")
        else:  # both
            where_conditions.append(f"({col_name} IS NULL OR CAST({col_name} AS TEXT) = '')")

    return {
        'table_name': category_config['table_name'],
        'date_column': category_config['date_column'],
        'where_conditions': where_conditions
    }


def get_null_check_columns(check_name):
    """
    특정 카테고리의 NULL 체크 컬럼 목록 반환 (하위 호환성)

    Args:
        check_name: 검증 카테고리

    Returns:
        dict: {
            'date_column': 'crawl_datetime',
            'columns': [
                {'name': 'item', 'check_empty': True},
                {'name': 'screen_size', 'check_empty': True},
                ...
            ]
        }
    """
    category_config = get_null_check_config(check_name)
    if not category_config:
        return None

    columns = []
    for col_name, col_config in category_config['columns'].items():
        check_type = col_config.get('check_type', 'both')
        columns.append({
            'name': col_name,
            'check_empty': check_type in ['empty', 'both']
        })

    return {
        'date_column': category_config['date_column'],
        'columns': columns
    }


def get_null_check_where_condition(check_name, check_column):
    """
    특정 컬럼의 NULL 검증 WHERE 조건 생성

    Args:
        check_name: 검증 카테고리 (예: 'amazon_tv')
        check_column: 검증 대상 컬럼

    Returns:
        str: WHERE 조건 (예: "(screen_size IS NULL OR CAST(screen_size AS TEXT) = '')")
    """
    config = get_null_check_config(check_name, check_column)
    if not config:
        # 기본값: 둘 다 체크
        return f"({check_column} IS NULL OR CAST({check_column} AS TEXT) = '')"

    check_type = config.get('check_type', 'both')

    if check_type == 'null':
        return f"{check_column} IS NULL"
    elif check_type == 'empty':
        return f"CAST({check_column} AS TEXT) = ''"
    else:  # both
        return f"({check_column} IS NULL OR CAST({check_column} AS TEXT) = '')"


def get_null_display_columns(check_name, check_column):
    """
    특정 카테고리/컬럼의 상세보기 표시 컬럼 목록 반환

    Args:
        check_name: 검증 카테고리
        check_column: 검증 대상 컬럼

    Returns:
        list: 표시 컬럼 목록 ['id', 'item', 'screen_size', ...]
    """
    config = get_null_check_config(check_name, check_column)
    if not config:
        return []
    return config.get('display_columns', [])


def get_null_query_columns(check_name, check_column):
    """
    특정 카테고리/컬럼의 복사 쿼리용 컬럼 목록 반환

    Args:
        check_name: 검증 카테고리
        check_column: 검증 대상 컬럼

    Returns:
        list: 쿼리 컬럼 목록 ['id', 'account_name', 'item', ...]
    """
    config = get_null_check_config(check_name, check_column)
    if not config:
        return []
    return config.get('query_columns', [])


def get_null_check_date_column(check_name):
    """
    특정 카테고리의 날짜 컬럼 반환

    Args:
        check_name: 검증 카테고리

    Returns:
        str: 날짜 컬럼명 (예: 'crawl_datetime')
    """
    config = get_null_check_config(check_name)
    if not config:
        return None
    return config.get('date_column')


def get_null_check_columns_for_category(check_name):
    """
    특정 카테고리의 모든 NULL 검증 대상 컬럼 목록 반환

    Args:
        check_name: 검증 카테고리

    Returns:
        list: 검증 대상 컬럼명 목록 ['item', 'screen_size', 'final_sku_price', ...]
    """
    config = get_null_check_config(check_name)
    if not config:
        return []
    return list(config.get('columns', {}).keys())


def get_all_check_names():
    """
    모든 검증 카테고리 목록 반환

    Returns:
        list: ['amazon_tv', 'bestbuy_tv', 'youtube_logs', ...]
    """
    config = load_null_check_config()
    return list(config.keys())


def get_all_categories():
    """
    모든 대시보드 카테고리(테이블 그룹) 목록 반환 (순서 유지)

    Returns:
        list: ['tv_retail', 'hhp_retail', 'youtube', 'market', ...]
    """
    config = load_null_check_config()
    categories = []
    for check_name, cat_config in config.items():
        category = cat_config.get('category', '')
        if category and category not in categories:
            categories.append(category)
    return categories


def get_check_names_by_category(category):
    """
    특정 카테고리(테이블 그룹)의 모든 check_name 목록 반환

    Args:
        category: 'tv_retail', 'hhp_retail', 'youtube', 'market' 등

    Returns:
        list: ['amazon_tv', 'bestbuy_tv', 'walmart_tv'] 등
    """
    config = load_null_check_config()
    return [
        check_name for check_name, cat_config in config.items()
        if cat_config.get('category') == category
    ]


def get_category_config(category):
    """
    특정 카테고리의 전체 설정 반환

    Args:
        category: 'tv_retail', 'youtube' 등

    Returns:
        dict: {
            'check_names': ['amazon_tv', 'bestbuy_tv', ...],
            'table_names': ['tv_retail_com'],
            'date_column': 'crawl_datetime'
        }
    """
    config = load_null_check_config()
    check_names = []
    table_names = set()
    date_column = None

    for check_name, cat_config in config.items():
        if cat_config.get('category') == category:
            check_names.append(check_name)
            table_names.add(cat_config['table_name'])
            if not date_column:
                date_column = cat_config.get('date_column')

    if not check_names:
        return None

    return {
        'check_names': check_names,
        'table_names': list(table_names),
        'date_column': date_column
    }


def get_check_name_by_table(table_name, retailer=None):
    """
    테이블명(과 리테일러명)으로 check_name 찾기

    Args:
        table_name: 'tv_retail_com', 'youtube_videos' 등
        retailer: 'Amazon', 'Bestbuy', 'Walmart' 등 (선택)

    Returns:
        str 또는 list:
            - retailer가 있으면 해당 check_name 반환
            - retailer가 없으면 해당 테이블의 모든 check_name 리스트 반환
    """
    config = load_null_check_config()
    matching_names = []

    for check_name, cat_config in config.items():
        if cat_config['table_name'] == table_name:
            matching_names.append(check_name)

    if not matching_names:
        return None

    if retailer:
        # 리테일러명으로 매칭 (amazon_tv, bestbuy_hhp 등)
        retailer_lower = retailer.lower()
        for check_name in matching_names:
            if check_name.startswith(retailer_lower):
                return check_name
        # 매칭 실패 시 첫번째 반환
        return matching_names[0] if matching_names else None

    return matching_names


def get_check_names_by_table(table_name):
    """
    특정 테이블의 모든 check_name 목록 반환

    Args:
        table_name: 'tv_retail_com', 'youtube_collection_logs' 등

    Returns:
        list: ['amazon_tv', 'bestbuy_tv', 'walmart_tv'] 등
    """
    config = load_null_check_config()
    return [
        check_name for check_name, cat_config in config.items()
        if cat_config['table_name'] == table_name
    ]


def reload_null_check_config():
    """캐시 초기화 후 다시 로드 (CSV 수정 시 사용)"""
    global _null_check_config_cache
    _null_check_config_cache = None
    return load_null_check_config()


# 하위 호환성을 위한 별칭
reload_null_display_config = reload_null_check_config


# ============================================================
# 중복검증 관련 함수
# dx_retail_columns.csv의 duplicate_key 사용
# ============================================================

def get_duplicate_key_columns(product_line):
    """
    특정 제품라인(tv/hhp)의 중복검증 키 컬럼 목록 반환

    Args:
        product_line: 'tv' 또는 'hhp'

    Returns:
        list: ['item', 'account_name'] 등 중복키 컬럼 목록
    """
    return get_retail_duplicate_keys(product_line)


def get_duplicate_check_query(product_line, use_period=False):
    """
    특정 제품라인의 중복검증 쿼리 생성

    Args:
        product_line: 'tv' 또는 'hhp'
        use_period: True면 오전/오후 구분 추가

    Returns:
        dict: {
            'table_name': 'tv_retail_com',
            'date_column': 'crawl_datetime',
            'duplicate_keys': ['item', 'account_name'],
            'group_by_sql': 'item, account_name'
        }
    """
    dup_keys = get_retail_duplicate_keys(product_line)
    if not dup_keys:
        return None

    # 테이블명과 날짜 컬럼 결정
    if product_line.lower() == 'tv':
        table_name = 'tv_retail_com'
        date_col = 'crawl_datetime'
    else:
        table_name = 'hhp_retail_com'
        date_col = 'crawl_strdatetime'

    # 오전/오후 구분
    if use_period and date_col:
        period_expr = f"CASE WHEN EXTRACT(HOUR FROM {date_col}::timestamp) < 12 THEN '오전' ELSE '오후' END"
        group_cols = dup_keys + ['period']
        group_by_sql = ', '.join(dup_keys) + f", {period_expr} as period"
    else:
        group_cols = dup_keys
        group_by_sql = ', '.join(dup_keys)

    return {
        'table_name': table_name,
        'date_column': date_col,
        'duplicate_keys': dup_keys,
        'group_by_columns': group_cols,
        'group_by_sql': group_by_sql,
        'use_period': use_period
    }


# ============================================================
# 형식검증 규칙 관련 함수
# ============================================================

import re

FORMAT_RULES_CSV_PATH = CSV_DIR / 'dx_format_rules.csv'
_format_rules_cache = None


def load_format_rules():
    """
    dx_format_rules.csv에서 형식검증 규칙 로드
    CSV 구조: table_name, product_line, column_name, retailer, validation_type, validation_rule, allowed_values, error_message

    Returns: {
        'tv_retail_com': {
            'ALL': {
                'item': [
                    {'retailer': 'common', 'type': 'regex', 'rule': '^[A-Za-z0-9]+$', 'allowed': [], 'error': 'item 형식 오류'},
                    ...
                ],
                ...
            },
            'TV': {...},
            'HHP': {...}
        },
        'youtube_videos': {...},
        ...
    }
    """
    global _format_rules_cache
    if _format_rules_cache is not None:
        return _format_rules_cache

    result = {}

    try:
        with open(FORMAT_RULES_CSV_PATH, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                table_name = row['table_name']
                product_line = row['product_line'].upper()  # TV, HHP, ALL
                column_name = row['column_name']
                retailer = row['retailer']
                validation_type = row['validation_type']
                validation_rule = row.get('validation_rule', '')
                allowed_values = row.get('allowed_values', '')
                error_message = row.get('error_message', '')

                if table_name not in result:
                    result[table_name] = {}
                if product_line not in result[table_name]:
                    result[table_name][product_line] = {}
                if column_name not in result[table_name][product_line]:
                    result[table_name][product_line][column_name] = []

                # allowed_values 파싱 (파이프 구분)
                allowed_list = [v.strip() for v in allowed_values.split('|') if v.strip()] if allowed_values else []

                result[table_name][product_line][column_name].append({
                    'retailer': retailer,
                    'type': validation_type,
                    'rule': validation_rule,
                    'allowed': allowed_list,
                    'error': error_message
                })

        _format_rules_cache = result
        print(f"[INFO] Format rules loaded from CSV: tables={list(result.keys())}")
    except Exception as e:
        print(f"[ERROR] Failed to load format rules CSV: {e}")

    return result


def get_format_rules(table_name, column_name, product_line='ALL'):
    """
    특정 테이블/필드의 형식검증 규칙 목록 반환

    Args:
        table_name: 테이블명 (예: 'tv_retail_com', 'youtube_videos')
        column_name: 필드명
        product_line: 'TV', 'HHP', 'ALL' (기본값 ALL)

    Returns:
        list: 검증 규칙 리스트 또는 빈 리스트
    """
    rules_data = load_format_rules()

    if table_name not in rules_data:
        return []

    table_rules = rules_data[table_name]
    result = []

    # product_line에 해당하는 규칙 추가
    product_key = product_line.upper()
    if product_key in table_rules and column_name in table_rules[product_key]:
        result.extend(table_rules[product_key][column_name])

    # ALL 규칙도 추가 (product_line이 ALL이 아닌 경우)
    if product_key != 'ALL' and 'ALL' in table_rules and column_name in table_rules['ALL']:
        result.extend(table_rules['ALL'][column_name])

    return result


def validate_field(table_name, field_name, value, account_name='Amazon', product_line='ALL'):
    """
    CSV 기반 필드 형식 검증

    Args:
        table_name: 테이블명 (예: 'tv_retail_com', 'hhp_retail_com', 'youtube_videos')
        field_name: 필드명
        value: 검증할 값
        account_name: 'Amazon', 'Bestbuy', 'Walmart', 'common' 등
        product_line: 'TV', 'HHP', 'ALL' (기본값 ALL)

    Returns:
        str: 오류 메시지 (오류 시) 또는 None (정상)
    """
    if value is None:
        return None
    val = str(value).strip()
    if val == '':
        return None

    rules = get_format_rules(table_name, field_name, product_line)
    if not rules:
        return None

    # 리테일러별 규칙과 common 규칙 분리
    retailer_rules = [r for r in rules if r['retailer'] == account_name]
    common_rules = [r for r in rules if r['retailer'] == 'common']

    # 리테일러별 규칙 먼저 적용 (allowed_values, allow_empty 등)
    for rule in retailer_rules:
        result = _apply_validation_rule(val, rule, field_name)
        if result is True:
            # 검증 통과 (allowed_values 등)
            return None
        elif result is not None:
            # 오류 발생
            return result

    # common 규칙 적용
    for rule in common_rules:
        result = _apply_validation_rule(val, rule, field_name)
        if result is True:
            return None
        elif result is not None:
            return result

    return None


def _apply_validation_rule(val, rule, field_name):
    """
    개별 검증 규칙 적용

    Returns:
        True: 검증 통과 (더 이상 검사 불필요)
        None: 이 규칙은 해당 안됨 (다음 규칙 검사 필요)
        str: 오류 메시지
    """
    rule_type = rule['type']
    rule_value = rule['rule']
    allowed = rule['allowed']
    error_msg = rule['error']

    # allowed_values: 허용값 목록에 있으면 통과
    if rule_type == 'allowed_values':
        if val in allowed:
            return True
        return None  # 다음 규칙 검사

    # allow_empty: 빈값이 아닌 경우만 다음 규칙 검사
    if rule_type == 'allow_empty':
        if not val:
            return True
        return None

    # regex: 정규식 패턴 매칭
    if rule_type == 'regex':
        if re.match(rule_value, val):
            return True
        return f'{error_msg}: {val[:20]}' if error_msg else None

    # regex_clean: 전처리 후 정규식 매칭
    if rule_type == 'regex_clean':
        clean_val = val
        clean_type = allowed[0] if allowed else ''

        if 'comma' in clean_type:
            clean_val = clean_val.replace(',', '')
        if 'plus' in clean_type:
            clean_val = clean_val.replace('+', '')
        if 'null' in clean_type:
            if val.lower() in ['null', 'none']:
                return True

        if re.match(rule_value, clean_val):
            return True
        return f'{error_msg}: {val[:20]}' if error_msg else None

    # range: 정수 범위 검증
    if rule_type == 'range':
        try:
            parts = rule_value.split('~')
            min_val, max_val = int(parts[0]), int(parts[1])
            num = int(val)
            if min_val <= num <= max_val:
                return True
            return f'{error_msg}: {val}' if error_msg else f'{field_name} 범위 오류'
        except ValueError:
            return f'{field_name} 숫자 아님: {val}'

    # range_float: 실수 범위 검증
    if rule_type == 'range_float':
        try:
            parts = rule_value.split('~')
            min_val, max_val = float(parts[0]), float(parts[1])
            num = float(val)
            if min_val <= num <= max_val:
                return True
            return f'{error_msg}: {val}' if error_msg else f'{field_name} 범위 오류'
        except ValueError:
            return f'{field_name} 형식 오류: {val[:20]}'

    # enum: 허용값 목록 검증
    if rule_type == 'enum':
        if val in allowed:
            return True
        return f'{error_msg}: {val}' if error_msg else None

    # starts_with: 시작 문자열 검증
    if rule_type == 'starts_with':
        if val.startswith(rule_value):
            return True
        return error_msg if error_msg else None

    # separator_count: 구분자 개수 검증 (예: |||~3)
    if rule_type == 'separator_count':
        try:
            parts = rule_value.split('~')
            separator, expected_count = parts[0], int(parts[1])
            actual_count = val.count(separator)
            if actual_count == expected_count:
                return True
            return f'{error_msg}' if error_msg else f'{field_name} 구분자 오류'
        except (ValueError, IndexError):
            return None

    return None


def reload_format_rules():
    """캐시 초기화 후 다시 로드 (CSV 수정 시 사용)"""
    global _format_rules_cache
    _format_rules_cache = None
    return load_format_rules()
