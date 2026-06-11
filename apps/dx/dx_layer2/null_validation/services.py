"""
NULL 검증 서비스 — 순수 비즈니스 로직 (DB cursor/conn을 받아 처리, HttpResponse 없음)
"""

import time
from datetime import datetime, timedelta
from apps.common.db import execute_dx_query, dx_table
from apps.common.response import log_error
from apps.common.retail_columns import load_retail_columns, get_editable_columns
from apps.dx.dx_layer2.common.context import get_status


# ==================== NULL 검증 설정 (monitoring_null_check 테이블) ====================

_CACHE_TTL = 60
_null_check_config_cache = None
_null_check_config_cache_time = None
EXCLUDED_RETAIL_TABLES = {'hhp_retail_com'}
EXCLUDED_RETAIL_CATEGORIES = {'hhp_retail'}


def load_null_check_config():
    """
    DB에서 NULL 검증 설정 로드 (3계층: 카테고리 → 그룹 → 컬럼)

    Returns: {
        'tv_retail': {
            'display_name': 'TV Retail',
            'display_order': 1,
            'has_retailer': True,
            'checks': {
                'amazon_tv': {
                    'display_name': 'Amazon',
                    'table_name': 'tv_retail_com',
                    'date_column': 'crawl_datetime',
                    'columns': {
                        'item': {'check_type': 'both', 'display_columns': [...], 'query_columns': [...]},
                        'screen_size': {...},
                    }
                },
                ...
            }
        },
        ...
    }
    """
    global _null_check_config_cache, _null_check_config_cache_time
    now = time.time()
    if _null_check_config_cache is not None and _null_check_config_cache_time and (now - _null_check_config_cache_time) < _CACHE_TTL:
        return _null_check_config_cache

    result = {}

    try:
        query = f"""
            SELECT c.category_name as category, c.display_name as cat_display_name,
                   c.display_order, c.has_retailer,
                   g.check_name, g.display_name as group_display_name,
                   g.table_name, g.date_column,
                   col.check_column, col.check_type,
                   col.display_columns, col.query_columns, col.query_days
            FROM {dx_table('monitoring_null_column')} col
            JOIN {dx_table('monitoring_null_group')} g ON g.id = col.group_id
            JOIN {dx_table('monitoring_null_category')} c ON c.id = g.category_id
            WHERE col.is_active = TRUE AND col.is_del = false
              AND g.is_active = TRUE AND g.is_del = false
              AND c.is_active = TRUE AND c.is_del = false
            ORDER BY c.display_order, g.display_order, col.id
        """
        rows = execute_dx_query(query)

        for row in rows:
            category = row.get('category', '')
            table_name = row.get('table_name', '')
            if category in EXCLUDED_RETAIL_CATEGORIES or table_name in EXCLUDED_RETAIL_TABLES:
                continue
            check_name = row['check_name']
            check_column = row['check_column']
            display_columns = row.get('display_columns', '') or ''
            query_columns = row.get('query_columns', '') or ''

            if category not in result:
                result[category] = {
                    'display_name': row.get('cat_display_name', ''),
                    'display_order': row.get('display_order', 0),
                    'has_retailer': row.get('has_retailer', False),
                    'checks': {}
                }

            if check_name not in result[category]['checks']:
                result[category]['checks'][check_name] = {
                    'display_name': row.get('group_display_name', ''),
                    'table_name': row['table_name'],
                    'date_column': row.get('date_column', ''),
                    'columns': {}
                }

            result[category]['checks'][check_name]['columns'][check_column] = {
                'check_type': row.get('check_type', 'both'),
                'display_columns': [col.strip() for col in display_columns.split('|') if col.strip()],
                'query_columns': [col.strip() for col in query_columns.split('|') if col.strip()],
                'query_days': int(row.get('query_days', 0) or 0)
            }

        _null_check_config_cache = result
        _null_check_config_cache_time = now
    except Exception as e:
        log_error(e, 'db')

    return result


def get_all_categories():
    """모든 대시보드 카테고리 목록 반환 (display_order 순)"""
    return list(load_null_check_config().keys())


def get_check_names_by_category(category):
    """특정 카테고리의 모든 check_name 목록 반환"""
    config = load_null_check_config()
    cat_config = config.get(category)
    if not cat_config:
        return []
    return list(cat_config['checks'].keys())


def get_null_check_config(category, check_name, check_column=None):
    """특정 check_name(또는 컬럼)의 NULL 검증 설정 반환"""
    config = load_null_check_config()
    cat_config = config.get(category)
    if not cat_config:
        return None
    check_config = cat_config['checks'].get(check_name)
    if not check_config:
        return None
    if check_column:
        col_config = check_config['columns'].get(check_column)
        if col_config:
            return {
                'table_name': check_config['table_name'],
                'date_column': check_config['date_column'],
                **col_config
            }
        return None
    return check_config


def reload_null_check_config():
    """캐시 초기화 후 다시 로드"""
    global _null_check_config_cache
    _null_check_config_cache = None
    return load_null_check_config()


# ==================== NULL 판정 공통 로직 ====================

def _build_null_sql_condition(col_name, check_type):
    """NULL 판정 SQL 조건 생성 (공통) — stats COUNT / detail WHERE 양쪽에서 사용"""
    if check_type == 'null':
        return f"{col_name} IS NULL"
    elif check_type == 'empty':
        return f"TRIM(CAST({col_name} AS TEXT)) = ''"
    else:  # both
        return f"({col_name} IS NULL OR TRIM(CAST({col_name} AS TEXT)) = '')"


def _is_field_null(val, check_type):
    """NULL 판정 Python 로직 (공통) — detail에서 레코드별 null_fields 판정에 사용"""
    if check_type == 'null':
        return val is None
    elif check_type == 'empty':
        return val is not None and str(val).strip() == ''
    else:  # both
        return val is None or str(val).strip() == ''


def get_null_check_query_parts(category, check_name):
    """NULL 체크 쿼리 파트 생성 (stats 건수 체크용)"""
    category_config = get_null_check_config(category, check_name)
    if not category_config:
        return None

    count_parts = []
    column_names = []

    for col_name, col_config in category_config['columns'].items():
        column_names.append(col_name)
        check_type = col_config.get('check_type', 'both')
        cond = _build_null_sql_condition(col_name, check_type)
        count_parts.append(f"COUNT(CASE WHEN {cond} THEN 1 END) as null_{col_name}")

    return {
        'table_name': category_config['table_name'],
        'date_column': category_config['date_column'],
        'count_parts': count_parts,
        'column_names': column_names
    }




def get_null_stats(cursor, target_date):
    """NULL 검증 통계 — 대시보드용"""
    total_null_issues = 0

    null_validation = {
        'type': 'null',
        'type_name': 'NULL 검증',
        'type_name_en': 'Null Validation',
        'description': '필수 필드의 NULL 또는 빈값 검증',
        'icon': '🔍',
        'tables': []
    }

    config = load_null_check_config()

    for category, cat_info in config.items():
        if not cat_info['checks']:
            continue

        display_name = cat_info['display_name']
        has_retailer = cat_info['has_retailer']

        cat_retailers = []
        cat_total_records = 0
        cat_total_issues = 0
        all_cat_fields = []

        for check_name, check_info in cat_info['checks'].items():
            query_parts = get_null_check_query_parts(category, check_name)
            if not query_parts:
                continue

            retailer_name = check_info['display_name']

            date_where = f"DATE({query_parts['date_column']}) = %s"
            params = [target_date]

            if has_retailer:
                date_where += " AND account_name = %s"
                params.append(retailer_name)

            query = f"""
                SELECT COUNT(*) as total,
                       {', '.join(query_parts['count_parts'])}
                FROM {query_parts['table_name']}
                WHERE {date_where}
            """
            cursor.execute(query, params)

            row = cursor.fetchone()

            if row:
                total = row[0] or 0
                fields_detail = {}
                total_null_count = 0
                for i, col_name in enumerate(query_parts['column_names']):
                    null_count = row[i + 1] or 0
                    fields_detail[col_name] = null_count
                    total_null_count += null_count
                    if col_name not in all_cat_fields:
                        all_cat_fields.append(col_name)

                # 정상처리(normal) 건 차감
                correction_where = "table_name = %s AND crawl_date = %s AND correction_type = 'null_check' AND status = 'normal'"
                correction_params = [query_parts['table_name'], str(target_date)]

                if has_retailer:
                    correction_where += " AND retailer = %s"
                    correction_params.append(retailer_name)

                cursor.execute(f"""
                    SELECT column_name, COUNT(*) FROM monitoring_corrections
                    WHERE {correction_where}
                    GROUP BY column_name
                """, correction_params)

                for correction_row in cursor.fetchall():
                    correction_col, correction_count = correction_row[0], correction_row[1]
                    if correction_col in fields_detail:
                        fields_detail[correction_col] = max(0, fields_detail[correction_col] - correction_count)
                        total_null_count = max(0, total_null_count - correction_count)

                cat_retailers.append({
                    'retailer': retailer_name,
                    'total': total,
                    'total_null_count': total_null_count,
                    'status': get_status(total_null_count),
                    'fields_detail': fields_detail
                })
                cat_total_records += total
                cat_total_issues += total_null_count

        null_validation['tables'].append({
            'table': category,
            'table_name': display_name,
            'total_records': cat_total_records,
            'total_issues': cat_total_issues,
            'status': get_status(cat_total_issues),
            'retailers': cat_retailers,
            'fields': all_cat_fields
        })
        total_null_issues += cat_total_issues

    null_validation['total_issues'] = total_null_issues
    null_validation['status'] = get_status(total_null_issues)
    return null_validation, total_null_issues


def get_null_detail(cursor, target_date, category, retailer, days, column):
    """NULL 필드 상세 조회 — 특정 컬럼의 NULL 행만 조회. dict 반환."""

    if category in EXCLUDED_RETAIL_CATEGORIES:
        return {'results': [], 'display_config': {}, 'query_config': {}, 'date': str(target_date)}

    next_date = target_date + timedelta(days=1)

    # 카테고리 정보 가져오기
    config = load_null_check_config()
    cat_info = config.get(category)
    if not cat_info or not cat_info['checks']:
        return {'results': [], 'display_config': {}, 'query_config': {}, 'date': str(target_date)}

    has_retailer = cat_info['has_retailer']

    # retailer 이름으로 check_name 매칭 (display_name 비교)
    check_name = None
    if retailer:
        for cn, check_info in cat_info['checks'].items():
            if check_info['display_name'].lower() == retailer.lower():
                check_name = cn
                break
    if not check_name:
        check_name = list(cat_info['checks'].keys())[0]

    # 설정 가져오기
    category_config = get_null_check_config(category, check_name)
    if not category_config or column not in category_config['columns']:
        return {'results': [], 'display_config': {}, 'query_config': {}, 'date': str(target_date)}

    col_config = category_config['columns'][column]
    actual_table = category_config['table_name']
    date_col = category_config.get('date_column', 'created_at')

    # WHERE 조건: 해당 컬럼만
    check_type = col_config.get('check_type', 'both')
    where_cond = _build_null_sql_condition(column, check_type)

    # 쿼리 생성 — 전체 컬럼 조회 (프론트 컬럼 선택 지원)
    if has_retailer:
        query = f"""
            SELECT *
            FROM {actual_table}
            WHERE {date_col}::timestamp >= %s AND {date_col}::timestamp < %s
              AND {where_cond}
        """
        params = [str(target_date), str(next_date)]
        if retailer:
            query += " AND account_name = %s"
            params.append(retailer)
        query += f" ORDER BY {date_col}"
    else:
        query = f"""
            SELECT *
            FROM {actual_table}
            WHERE DATE({date_col}) = %s
              AND {where_cond}
            ORDER BY {date_col} DESC
        """
        params = [target_date]

    cursor.execute(query, params)
    select_cols = [desc[0] for desc in cursor.description]
    rows = cursor.fetchall()

    # 컬럼 인덱스 매핑
    col_index = {col: idx for idx, col in enumerate(select_cols)}

    # 정상 처리(normal) 건 조회 — 확장 조회 전에 실행하여 정상처리 item 제외
    normal_set = set()
    normal_reviews = {}
    cursor.execute("""
        SELECT record_id, column_name, memo, created_id, created_at, reason
        FROM monitoring_corrections
        WHERE table_name = %s AND crawl_date = %s AND column_name = %s
          AND correction_type = 'null_check' AND status = 'normal'
    """, (actual_table, str(target_date), column))
    for nr_row in cursor.fetchall():
        normal_set.add(nr_row[0])  # record_id만
        normal_reviews[f"{nr_row[0]}_{nr_row[1]}"] = {
            'memo': nr_row[2],
            'created_id': nr_row[3],
            'created_at': nr_row[4].strftime('%Y-%m-%d %H:%M:%S') if nr_row[4] else None,
            'reason': nr_row[5]
        }

    # retail + days > 1: 오류 item 추출 후 N일치 확장 조회
    is_expanded = False
    id_idx = col_index['id']
    if has_retailer and days > 1 and rows:
        item_idx = select_cols.index('item') if 'item' in select_cols else None
        if item_idx is not None:
            # 정상처리 건 제외 후 에러 item 추출
            error_items = list(set(r[item_idx] for r in rows if r[item_idx] and r[id_idx] not in normal_set))
            if error_items:
                start_date = target_date - timedelta(days=days - 1)
                placeholders = ', '.join(['%s'] * len(error_items))
                expand_query = f"""
                    SELECT *
                    FROM {actual_table}
                    WHERE {date_col}::timestamp >= %s AND {date_col}::timestamp < %s
                      AND account_name = %s
                      AND item IN ({placeholders})
                    ORDER BY item, {date_col}
                """
                expand_params = [str(start_date), str(next_date), retailer] + error_items
                cursor.execute(expand_query, expand_params)
                rows = cursor.fetchall()
                is_expanded = True

    results = []
    col_idx = col_index.get(column)
    for row in rows:
        # 정상처리 건이면 스킵
        if row[id_idx] in normal_set:
            continue

        # 확장 조회(days > 1)면 전체 이력 표시, 1일치면 NULL만 필터
        if not is_expanded:
            if col_idx is not None and not _is_field_null(row[col_idx], check_type):
                continue

        record_data = {}
        for col_name in select_cols:
            idx = col_index.get(col_name)
            if idx is not None:
                val = row[idx]
                if isinstance(val, datetime):
                    record_data[col_name] = val.strftime('%Y-%m-%d %H:%M:%S')
                else:
                    record_data[col_name] = val
        record_data['null_fields'] = [column] if (col_idx is not None and _is_field_null(row[col_idx], check_type)) else []
        results.append(record_data)

    # display_config, query_config 생성
    display_config = {}
    query_config = {}
    display_cols = col_config.get('display_columns', [])
    query_cols = col_config.get('query_columns', [])
    if display_cols:
        display_config[column] = {'select_columns': display_cols}
    if query_cols:
        query_config[column] = query_cols

    # 리테일러 전체 수집항목 컬럼 + 수정 가능 컬럼
    all_retail_cols = []
    editable_cols = []
    if has_retailer and retailer:
        product_line = 'tv' if category == 'tv_retail' else 'hhp'
        retail_cols_data = load_retail_columns()
        all_retail_cols = retail_cols_data.get(product_line, {}).get(retailer, [])
        editable_cols = get_editable_columns(product_line, retailer)

    return {
        'results': results,
        'select_cols': all_retail_cols,
        'editable_cols': editable_cols,
        'actual_table': actual_table,
        'display_config': display_config,
        'query_config': query_config,
        'normal_reviews': normal_reviews,
        'date_column': date_col,
        'date': str(target_date)
    }


# null_review 테이블 화이트리스트
VALID_TABLES_UPDATE = {
    'tv_retail_com',
    'youtube_collection_logs', 'youtube_videos', 'youtube_comments',
    'market_trend', 'market_comp_product', 'market_comp_event', 'openai_forecast_results',
}


def save_null_review(cursor, conn, table_name, record_id, column_name, status, memo, reason, crawl_date, correction_type, username):
    """NULL 검증 정상 처리 저장. dict 반환."""

    valid_correction_types = {'null': 'null_check', 'format': 'format_check', 'duplicate': 'duplicate_check'}
    correction_type_value = valid_correction_types.get(correction_type, 'null_check')

    if not all([table_name, record_id, column_name, status]):
        return {'error': '필수 파라미터 누락', 'status_code': 400}

    # 정상 처리만 허용 (reverted 불가)
    if status != 'normal':
        return {'error': '잘못된 status 값', 'status_code': 400}

    if not reason:
        return {'error': '이유 선택은 필수입니다', 'status_code': 400}

    if table_name not in VALID_TABLES_UPDATE:
        return {'error': '허용되지 않는 테이블', 'status_code': 400}

    # 현재 값 + account_name + item 조회
    cursor.execute(
        f"SELECT {column_name}, account_name, item FROM {table_name} WHERE id = %s",
        (record_id,)
    )
    row = cursor.fetchone()
    if not row:
        return {'error': '해당 레코드가 없습니다', 'status_code': 404}

    old_value = row[0]
    retailer = row[1]
    item_value = str(row[2]) if row[2] else None

    # 중복 정상처리 체크
    cursor.execute("""
        SELECT id FROM monitoring_corrections
        WHERE table_name = %s AND record_id = %s AND column_name = %s
          AND correction_type = %s AND status = 'normal' AND crawl_date = %s
    """, (table_name, record_id, column_name, correction_type_value, str(crawl_date)))
    if cursor.fetchone():
        return {'error': '이미 정상처리된 항목입니다', 'status_code': 400}

    now = datetime.now()

    # monitoring_corrections에 이력 저장 (실제 데이터는 수정하지 않음)
    cursor.execute("""
        INSERT INTO monitoring_corrections
            (layer, correction_type, table_name, record_id, column_name,
             old_value, new_value, crawl_date, created_id, created_at, status, memo, reason, retailer, item)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, (
        2, correction_type_value, table_name, record_id, column_name,
        str(old_value) if old_value is not None else None,
        None,
        crawl_date, username, now, status, memo or None,
        reason or None, retailer or None, item_value
    ))

    conn.commit()

    return {'success': True, 'status': status}
