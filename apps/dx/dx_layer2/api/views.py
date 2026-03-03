"""
Layer 2 API: 형식/NULL 검증 (Formatting & Null Validation)
- 검증유형별 분류: NULL검증, 형식검증, 이상치검증
- 테이블별 분류: TV Retail, HHP Retail, Sentiment, YouTube, Market
"""

from django.http import JsonResponse
from datetime import datetime, timedelta
from apps.common.db import get_dx_connection, dx_table
from apps.common.response import safe_error, log_error
from apps.common.params import parse_date
from apps.common.retail_columns import (
    get_null_check_query_parts, get_null_detail_query_parts, get_null_check_columns,
    validate_field, get_duplicate_key_columns, get_duplicate_check_query,
    build_format_error_sql, build_per_field_error_sql, get_retailer_list, get_retail_duplicate_keys,
    get_null_check_config, get_null_display_columns, get_null_query_columns,
    get_null_check_where_condition, get_null_check_date_column,
    get_check_name_by_table, get_check_names_by_table, get_null_check_columns_for_category,
    get_all_categories, get_check_names_by_category, get_category_config,
    load_retail_columns, get_editable_columns
)


# table 파라미터 화이트리스트
VALID_TABLES_FORMAT = {'tv_retail', 'hhp_retail', 'youtube_logs', 'youtube_videos', 'youtube_comments', 'youtube', 'market'}
VALID_TABLES_ANOMALY = {'tv_retail', 'hhp_retail', 'youtube_videos', 'youtube_logs', 'market_trend', 'market_product', 'market_event'}
VALID_TABLES_RETAILER = {'TV Retail', 'HHP Retail'}
VALID_TABLES_RULES = {'tv_retail_com', 'hhp_retail_com', 'youtube_collection_logs', 'youtube_videos', 'youtube_comments', 'market_trend', 'market_comp_product', 'market_comp_event', 'openai_forecast_results'}


# 상태 기준: 0건 = OK, 1~10건 = WARNING, 10건 초과 = CRITICAL
def get_status(issue_count):
    if issue_count == 0:
        return 'OK'
    elif issue_count <= 10:
        return 'WARNING'
    else:
        return 'CRITICAL'


def validate_tv_field(field_name, value, account_name='Amazon'):
    """TV Retail 필드별 형식 검증. 오류 시 메시지 반환, 정상이면 None (CSV 기반)"""
    return validate_field('tv_retail_com', field_name, value, account_name, product_line='TV')


def validate_hhp_field(field_name, value, account_name='Amazon'):
    """HHP Retail 필드별 형식 검증. 오류 시 메시지 반환, 정상이면 None (CSV 기반)"""
    return validate_field('hhp_retail_com', field_name, value, account_name, product_line='HHP')


def layer_stats(request):
    """Layer 2 통계 API - 검증유형별, 테이블별 구조화"""
    target_date = parse_date(request.GET.get('date'))
    if target_date is None:
        return JsonResponse({'error': '날짜 형식이 올바르지 않습니다.'}, status=400)

    next_date = target_date + timedelta(days=1)

    results = {
        'timestamp': datetime.now().isoformat(),
        'date': str(target_date),
        'layer': 2,
        'name': '형식/NULL 검수',
        'validation_types': [],
        'summary': {
            'total_issues': 0,
            'null_issues': 0,
            'format_issues': 0,
            'duplicate_issues': 0,
            'overall_status': 'OK'
        }
    }

    conn = None
    cursor = None
    try:
        conn = get_dx_connection()
        cursor = conn.cursor()

        total_null_issues = 0
        total_format_issues = 0
        total_anomaly_issues = 0

        # ============================================================
        # 1. NULL 검증 (필수값 누락) - CSV 기반 동적 생성
        # ============================================================
        null_validation = {
            'type': 'null',
            'type_name': 'NULL 검증',
            'type_name_en': 'Null Validation',
            'description': '필수 필드의 NULL 또는 빈값 검증',
            'icon': '🔍',
            'tables': []
        }

        # DB에서 모든 category 가져와서 동적으로 테이블 생성
        all_categories = get_all_categories()

        # category별 표시명 매핑 (category -> display_name)
        category_display_names = {
            'tv_retail': 'TV Retail',
            'hhp_retail': 'HHP Retail',
            'youtube': 'YouTube',
            'market': 'Market'
        }

        # 리테일러 테이블 (account_name 조건 필요)
        retail_categories = ['tv_retail', 'hhp_retail']

        for category in all_categories:
            try:
                check_names = get_check_names_by_category(category)
                if not check_names:
                    continue

                cat_retailers = []
                cat_total_records = 0
                cat_total_issues = 0
                all_cat_fields = []

                # 표시명 결정 (매핑에 없으면 category 그대로 사용)
                display_name = category_display_names.get(category, category.replace('_', ' ').title())

                for check_name in check_names:
                    try:
                        query_parts = get_null_check_query_parts(check_name)
                        if not query_parts:
                            continue

                        # 리테일러명 추출 (check_name에서 추출)
                        # tv_retail, hhp_retail: amazon_tv -> Amazon
                        # youtube: youtube_logs -> Logs
                        # market: market_trend -> Trend
                        if category in retail_categories:
                            retailer_name = check_name.split('_')[0].capitalize()
                        else:
                            # check_name에서 category 부분 제거하고 표시명 생성
                            parts = check_name.split('_')
                            if len(parts) > 1 and parts[0] == category.split('_')[0]:
                                retailer_name = '_'.join(parts[1:]).replace('_', ' ').title()
                            else:
                                retailer_name = check_name.replace('_', ' ').title()

                        # 상세 쿼리 파트도 가져옴 (WHERE 조건용)
                        detail_parts = get_null_detail_query_parts(check_name)
                        where_conds = ' OR '.join(detail_parts['where_conditions']) if detail_parts else '1=0'

                        # 필드별 NULL 건수와 NULL 레코드 수를 동시에 조회
                        if category in retail_categories:
                            # 리테일러 테이블: account_name 조건 추가
                            query = f"""
                                SELECT COUNT(*) as total,
                                       {', '.join(query_parts['count_parts'])},
                                       COUNT(CASE WHEN {where_conds} THEN 1 END) as records_with_null
                                FROM {query_parts['table_name']}
                                WHERE DATE({query_parts['date_column']}::timestamp) = %s
                                  AND account_name = %s
                            """
                            cursor.execute(query, (target_date, retailer_name))
                        else:
                            # 그 외 테이블: account_name 조건 없음
                            query = f"""
                                SELECT COUNT(*) as total,
                                       {', '.join(query_parts['count_parts'])},
                                       COUNT(CASE WHEN {where_conds} THEN 1 END) as records_with_null
                                FROM {query_parts['table_name']}
                                WHERE DATE({query_parts['date_column']}) = %s
                            """
                            cursor.execute(query, (target_date,))

                        row = cursor.fetchone()

                        if row:
                            total = row[0] or 0
                            fields_detail = {}
                            total_null_count = 0  # 모든 필드의 NULL 건수 합산
                            for i, col_name in enumerate(query_parts['column_names']):
                                null_count = row[i + 1] or 0
                                fields_detail[col_name] = null_count
                                total_null_count += null_count  # NULL 건수 합산
                                if col_name not in all_cat_fields:
                                    all_cat_fields.append(col_name)

                            # 정상 처리(normal) 건수 차감
                            try:
                                cursor.execute("""
                                    SELECT column_name, COUNT(*) FROM monitoring_corrections
                                    WHERE table_name = %s AND crawl_date = %s
                                      AND correction_type = 'null_check' AND status = 'normal'
                                    GROUP BY column_name
                                """, (query_parts['table_name'], str(target_date)))
                                for nc_row in cursor.fetchall():
                                    nc_col, nc_count = nc_row[0], nc_row[1]
                                    if nc_col in fields_detail:
                                        fields_detail[nc_col] = max(0, fields_detail[nc_col] - nc_count)
                                        total_null_count = max(0, total_null_count - nc_count)
                            except Exception:
                                pass

                            cat_retailers.append({
                                'retailer': retailer_name,
                                'total': total,
                                'records_with_null': total_null_count,  # 필드별 NULL 합산 (정상건 차감)
                                'status': get_status(total_null_count),
                                'fields_detail': fields_detail
                            })
                            cat_total_records += total
                            cat_total_issues += total_null_count
                    except Exception as e:
                        print(f'[WARN] layer_stats check_name={check_name}: {e}')
                        pass

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
            except Exception as e:
                print(f'[WARN] layer_stats category={category}: {e}')
                pass

        null_validation['total_issues'] = total_null_issues
        null_validation['status'] = get_status(total_null_issues)
        results['validation_types'].append(null_validation)

        # ============================================================
        # 2. 형식 검증 (데이터 포맷 오류) - 리테일러별 검증
        # ============================================================
        format_validation = {
            'type': 'format',
            'type_name': '형식 검증',
            'type_name_en': 'Format Validation',
            'description': '데이터 형식 및 패턴 검증',
            'icon': '📋',
            'tables': []
        }

        # tv_item_mst에서 유효한 item 목록 조회 (TV Retail 참조 무결성 검증용)
        cursor.execute("SELECT DISTINCT item FROM tv_item_mst")
        tv_valid_items = set(row[0] for row in cursor.fetchall())

        # TV Retail 형식 검증 - 리테일러별 전체 필드 검증 (청크 단위 전수검사)
        tv_format_errors = []
        tv_format_by_retailer = {'Amazon': 0, 'Bestbuy': 0, 'Walmart': 0}
        tv_format_total_by_retailer = {'Amazon': 0, 'Bestbuy': 0, 'Walmart': 0}
        tv_format_rows_count = 0

        # 전체 필드 목록
        all_fields = [
            'item', 'page_type', 'product_url', 'main_rank', 'bsr_rank',
            'final_sku_price', 'original_sku_price',
            'count_of_reviews', 'star_rating', 'count_of_star_ratings',
            'detailed_review_content',
            'number_of_units_purchased_past_month', 'available_quantity_for_purchase',
            'sku_popularity', 'retailer_membership_discounts',
            'rank_1', 'rank_2', 'summarized_review_content',
            'savings', 'offer', 'retailer_sku_name_similar', 'recommendation_intent',
            'number_of_ppl_purchased_yesterday', 'number_of_ppl_added_to_carts', 'discount_type'
        ]

        CHUNK_SIZE = 5000
        tv_offset = 0
        while True:
            cursor.execute("""
                SELECT
                    account_name, id, item, page_type, product_url,
                    main_rank, bsr_rank, final_sku_price, original_sku_price,
                    count_of_reviews, star_rating, count_of_star_ratings,
                    detailed_review_content,
                    number_of_units_purchased_past_month, available_quantity_for_purchase,
                    sku_popularity, retailer_membership_discounts,
                    rank_1, rank_2, summarized_review_content,
                    savings, offer, retailer_sku_name_similar, recommendation_intent,
                    number_of_ppl_purchased_yesterday, number_of_ppl_added_to_carts, discount_type
                FROM tv_retail_com
                WHERE DATE(crawl_datetime::timestamp) = %s
                ORDER BY id
                LIMIT %s OFFSET %s
            """, (target_date, CHUNK_SIZE, tv_offset))

            chunk = cursor.fetchall()
            if not chunk:
                break
            tv_format_rows_count += len(chunk)

            for row in chunk:
                account_name = row[0] or 'Unknown'
                item_value = row[2]
                errors = []

                # 리테일러별 총 레코드 수 카운트
                if account_name in tv_format_total_by_retailer:
                    tv_format_total_by_retailer[account_name] += 1
                else:
                    tv_format_total_by_retailer[account_name] = 1

                # row[2]부터 시작 (row[0]=account_name, row[1]=id)
                values = list(row[2:])

                for field, value in zip(all_fields, values):
                    error = validate_tv_field(field, value, account_name)
                    if error:
                        errors.append({'field': field, 'value': str(value)[:30] if value else '', 'error': error})

                # 참조 무결성 검증: item이 tv_item_mst에 존재하는지
                if item_value and item_value not in tv_valid_items:
                    errors.append({
                        'field': 'item (참조 무결성)',
                        'value': str(item_value)[:30],
                        'error': '마스터 테이블에 등록되지 않은 item'
                    })

                if errors:
                    if len(tv_format_errors) < 30:
                        tv_format_errors.append({
                            'id': row[1],
                            'account_name': account_name,
                            'item': row[2],
                            'errors': errors[:5]
                        })
                    if account_name in tv_format_by_retailer:
                        tv_format_by_retailer[account_name] += len(errors)
                    else:
                        tv_format_by_retailer[account_name] = len(errors)

            tv_offset += CHUNK_SIZE

        tv_format_retailers = []
        tv_format_issue_total = 0
        for retailer, count in tv_format_by_retailer.items():
            tv_format_retailers.append({
                'retailer': retailer,
                'total': tv_format_total_by_retailer.get(retailer, 0),
                'issue_count': count,
                'status': get_status(count)
            })
            tv_format_issue_total += count

        format_validation['tables'].append({
            'table': 'tv_retail',
            'table_name': 'TV Retail',
            'total_checked': tv_format_rows_count,
            'total_issues': tv_format_issue_total,
            'status': get_status(tv_format_issue_total),
            'retailers': tv_format_retailers,
            'sample_errors': tv_format_errors
        })
        total_format_issues += tv_format_issue_total

        # hhp_item_mst에서 유효한 item 목록 조회 (HHP Retail 참조 무결성 검증용)
        cursor.execute("SELECT DISTINCT item FROM hhp_item_mst")
        hhp_valid_items = set(row[0] for row in cursor.fetchall())

        # HHP Retail 형식 검증 - 리테일러별 전체 필드 검증 (청크 단위 전수검사)
        hhp_format_errors = []
        hhp_format_by_retailer = {'Amazon': 0, 'Bestbuy': 0, 'Walmart': 0}
        hhp_format_total_by_retailer = {'Amazon': 0, 'Bestbuy': 0, 'Walmart': 0}
        hhp_format_rows_count = 0

        # HHP 전용 필드 목록 (trend_rank, trade_in, sku_status 포함 - 쿼리 순서와 일치)
        hhp_fields = [
            'item', 'page_type', 'product_url', 'main_rank', 'bsr_rank', 'trend_rank',
            'final_sku_price', 'original_sku_price',
            'count_of_reviews', 'star_rating', 'count_of_star_ratings',
            'detailed_review_content', 'trade_in', 'sku_status',
            'number_of_units_purchased_past_month', 'available_quantity_for_purchase',
            'sku_popularity', 'retailer_membership_discounts',
            'rank_1', 'rank_2', 'summarized_review_content',
            'savings', 'offer', 'retailer_sku_name_similar', 'recommendation_intent',
            'number_of_ppl_purchased_yesterday', 'number_of_ppl_added_to_carts', 'discount_type'
        ]

        hhp_offset = 0
        while True:
            cursor.execute("""
                SELECT
                    account_name, id, item, page_type, product_url,
                    main_rank, bsr_rank, trend_rank, final_sku_price, original_sku_price,
                    count_of_reviews, star_rating, count_of_star_ratings,
                    detailed_review_content, trade_in, sku_status,
                    number_of_units_purchased_past_month, available_quantity_for_purchase,
                    sku_popularity, retailer_membership_discounts,
                    rank_1, rank_2, summarized_review_content,
                    savings, offer, retailer_sku_name_similar, recommendation_intent,
                    number_of_ppl_purchased_yesterday, number_of_ppl_added_to_carts, discount_type
                FROM hhp_retail_com
                WHERE DATE(crawl_strdatetime::timestamp) = %s
                ORDER BY id
                LIMIT %s OFFSET %s
            """, (target_date, CHUNK_SIZE, hhp_offset))

            chunk = cursor.fetchall()
            if not chunk:
                break
            hhp_format_rows_count += len(chunk)

            for row in chunk:
                account_name = row[0] or 'Unknown'
                item_value = row[2]
                errors = []

                # 리테일러별 총 레코드 수 카운트
                if account_name in hhp_format_total_by_retailer:
                    hhp_format_total_by_retailer[account_name] += 1
                else:
                    hhp_format_total_by_retailer[account_name] = 1

                # row[2]부터 시작 (row[0]=account_name, row[1]=id)
                values = list(row[2:])

                for field, value in zip(hhp_fields, values):
                    error = validate_hhp_field(field, value, account_name)
                    if error:
                        errors.append({'field': field, 'value': str(value)[:30] if value else '', 'error': error})

                # 참조 무결성 검증: item이 hhp_item_mst에 존재하는지
                if item_value and item_value not in hhp_valid_items:
                    errors.append({
                        'field': 'item (참조 무결성)',
                        'value': str(item_value)[:30],
                        'error': '마스터 테이블에 등록되지 않은 item'
                    })

                if errors:
                    if len(hhp_format_errors) < 30:
                        hhp_format_errors.append({
                            'id': row[1],
                            'account_name': account_name,
                            'item': row[2],
                            'errors': errors[:5]
                        })
                    if account_name in hhp_format_by_retailer:
                        hhp_format_by_retailer[account_name] += len(errors)
                    else:
                        hhp_format_by_retailer[account_name] = len(errors)

            hhp_offset += CHUNK_SIZE

        hhp_format_retailers = []
        hhp_format_issue_total = 0
        for retailer, count in hhp_format_by_retailer.items():
            hhp_format_retailers.append({
                'retailer': retailer,
                'total': hhp_format_total_by_retailer.get(retailer, 0),
                'issue_count': count,
                'status': get_status(count)
            })
            hhp_format_issue_total += count

        format_validation['tables'].append({
            'table': 'hhp_retail',
            'table_name': 'HHP Retail',
            'total_checked': hhp_format_rows_count,
            'total_issues': hhp_format_issue_total,
            'status': get_status(hhp_format_issue_total),
            'retailers': hhp_format_retailers,
            'sample_errors': hhp_format_errors
        })
        total_format_issues += hhp_format_issue_total

        # YouTube 형식 검증 — 규칙 테이블 기반 (Logs, Videos, Comments)
        yt_tables = [
            ('youtube_collection_logs', 'Logs', 'started_at'),
            ('youtube_videos', 'Videos', 'created_at'),
            ('youtube_comments', 'Comments', 'created_at'),
        ]
        yt_total_format_issues = 0
        yt_total_format_checked = 0
        youtube_format_retailers = []

        for yt_table, yt_retailer, yt_date_col in yt_tables:
            cursor.execute(f"SELECT COUNT(*) FROM {yt_table} WHERE DATE({yt_date_col}) = %s", (target_date,))
            yt_total = cursor.fetchone()[0] or 0

            error_where = build_format_error_sql(yt_table, 'ALL', yt_retailer)
            if error_where != 'FALSE':
                cursor.execute(f"SELECT COUNT(*) FROM {yt_table} WHERE DATE({yt_date_col}) = %s AND ({error_where})", (target_date,))
                yt_issues = cursor.fetchone()[0] or 0
            else:
                yt_issues = 0

            yt_total_format_checked += yt_total
            yt_total_format_issues += yt_issues
            youtube_format_retailers.append({
                'retailer': yt_retailer,
                'total': yt_total,
                'issue_count': yt_issues,
                'status': get_status(yt_issues),
            })

        format_validation['tables'].append({
            'table': 'youtube',
            'table_name': 'YouTube',
            'total_checked': yt_total_format_checked,
            'total_issues': yt_total_format_issues,
            'status': get_status(yt_total_format_issues),
            'retailers': youtube_format_retailers
        })
        total_format_issues += yt_total_format_issues

        # Market 형식 검증 — 규칙 테이블 기반 (Trend, Comp Product, Comp Event, Forecast)
        try:
            market_tables = [
                ('market_trend', 'Trend', 'crawl_at_local_time'),
                ('market_comp_product', 'Comp Product', 'created_at'),
                ('market_comp_event', 'Comp Event', 'created_at'),
                ('openai_forecast_results', 'Forecast', 'crawled_at'),
            ]
            market_total_format_issues = 0
            market_total_format_checked = 0
            market_format_retailers = []

            for mkt_table, mkt_retailer, mkt_date_col in market_tables:
                cursor.execute(f"SELECT COUNT(*) FROM {mkt_table} WHERE DATE({mkt_date_col}) = %s", (target_date,))
                mkt_total = cursor.fetchone()[0] or 0

                error_where = build_format_error_sql(mkt_table, 'ALL', mkt_retailer)
                if error_where != 'FALSE':
                    cursor.execute(f"SELECT COUNT(*) FROM {mkt_table} WHERE DATE({mkt_date_col}) = %s AND ({error_where})", (target_date,))
                    mkt_issues = cursor.fetchone()[0] or 0
                else:
                    mkt_issues = 0

                market_total_format_checked += mkt_total
                market_total_format_issues += mkt_issues
                market_format_retailers.append({
                    'retailer': mkt_retailer,
                    'total': mkt_total,
                    'issue_count': mkt_issues,
                    'status': get_status(mkt_issues),
                })

            format_validation['tables'].append({
                'table': 'market',
                'table_name': 'Market',
                'total_checked': market_total_format_checked,
                'total_issues': market_total_format_issues,
                'status': get_status(market_total_format_issues),
                'retailers': market_format_retailers
            })
            total_format_issues += market_total_format_issues
        except Exception as e:
            print(f'[WARN] layer_stats market_format: {e}')

        format_validation['total_issues'] = total_format_issues
        format_validation['status'] = get_status(total_format_issues)
        results['validation_types'].append(format_validation)

        # ============================================================
        # 3. 중복 검증 (동일 상품 중복 수집) - CSV 기반
        # ============================================================
        anomaly_validation = {
            'type': 'duplicate',
            'type_name': '중복 검증',
            'type_name_en': 'Duplicate Validation',
            'description': '동일 시간대 동일 상품 중복 수집 탐지',
            'icon': '🔄',
            'tables': []
        }

        def get_duplicate_count(table_name, date_col, dup_keys, target_date, use_period=False, group_by_col=None):
            """CSV 기반 중복 검증 쿼리 실행"""
            dup_keys_sql = ', '.join(dup_keys)

            if use_period:
                period_expr = f"CASE WHEN EXTRACT(HOUR FROM {date_col}::timestamp) < 12 THEN '오전' ELSE '오후' END as period"
                if group_by_col:
                    # 리테일러별 그룹화
                    cursor.execute(f"""
                        SELECT {group_by_col}, COUNT(*) as dup_groups FROM (
                            SELECT {dup_keys_sql}, {period_expr}
                            FROM {table_name}
                            WHERE DATE({date_col}::timestamp) = %s
                            GROUP BY {dup_keys_sql}, period
                            HAVING COUNT(*) > 1
                        ) sub
                        GROUP BY {group_by_col}
                        ORDER BY {group_by_col}
                    """, (target_date,))
                    return {row[0]: row[1] for row in cursor.fetchall()}
                else:
                    cursor.execute(f"""
                        SELECT COUNT(*) FROM (
                            SELECT {dup_keys_sql}, {period_expr}
                            FROM {table_name}
                            WHERE DATE({date_col}::timestamp) = %s
                            GROUP BY {dup_keys_sql}, period
                            HAVING COUNT(*) > 1
                        ) sub
                    """, (target_date,))
                    return cursor.fetchone()[0] or 0
            else:
                cursor.execute(f"""
                    SELECT COUNT(*) FROM (
                        SELECT {dup_keys_sql}
                        FROM {table_name}
                        WHERE DATE({date_col}) = %s
                        GROUP BY {dup_keys_sql}
                        HAVING COUNT(*) > 1
                    ) sub
                """, (target_date,))
                return cursor.fetchone()[0] or 0

        # TV Retail 중복 검증 (CSV 기반)
        tv_dup_keys = get_retail_duplicate_keys('tv')
        if not tv_dup_keys:
            tv_dup_keys = ['item', 'account_name']
        tv_date_col = 'crawl_datetime'

        cursor.execute(f"SELECT COUNT(*) FROM tv_retail_com WHERE DATE({tv_date_col}::timestamp) = %s", (target_date,))
        tv_total_records = cursor.fetchone()[0] or 0

        retailer_list = get_retailer_list()
        tv_dup_dict = get_duplicate_count('tv_retail_com', tv_date_col, tv_dup_keys, target_date, use_period=True, group_by_col='account_name')

        # 중복검증 정상처리 건수 차감
        tv_dup_normal = {}
        try:
            cursor.execute("""
                SELECT retailer, COUNT(*) FROM monitoring_corrections
                WHERE table_name = 'tv_retail_com' AND crawl_date = %s
                  AND correction_type = 'duplicate_check' AND status = 'normal'
                GROUP BY retailer
            """, (str(target_date),))
            for nr in cursor.fetchall():
                tv_dup_normal[nr[0]] = nr[1]
        except Exception:
            pass

        tv_dup_retailers = []
        tv_dup_total = 0
        for retailer_name in retailer_list:
            dup_count = max(0, tv_dup_dict.get(retailer_name, 0) - tv_dup_normal.get(retailer_name, 0))
            tv_dup_retailers.append({
                'retailer': retailer_name,
                'duplicate_groups': dup_count,
                'status': get_status(dup_count)
            })
            tv_dup_total += dup_count

        # TV Retail 가격 이상
        cursor.execute("""
            SELECT COUNT(*) FROM tv_retail_com
            WHERE DATE(crawl_datetime::timestamp) = %s
            AND final_sku_price ~ '^\$[\d,]+\.?\d*$'
            AND (
                CAST(REPLACE(REPLACE(final_sku_price, '$', ''), ',', '') AS DECIMAL) < 0
                OR CAST(REPLACE(REPLACE(final_sku_price, '$', ''), ',', '') AS DECIMAL) > 50000
            )
        """, (target_date,))
        tv_price_anomaly = cursor.fetchone()[0] or 0

        anomaly_validation['tables'].append({
            'table': 'tv_retail',
            'table_name': 'TV Retail',
            'total_records': tv_total_records,
            'total_issues': tv_dup_total,
            'duplicate_groups': tv_dup_total,
            'duplicate_keys': tv_dup_keys,
            'status': get_status(tv_dup_total),
            'retailers': tv_dup_retailers
        })
        total_anomaly_issues += tv_dup_total

        # HHP Retail 중복 검증 (CSV 기반)
        hhp_dup_keys = get_retail_duplicate_keys('hhp')
        if not hhp_dup_keys:
            hhp_dup_keys = ['item', 'account_name']
        hhp_date_col = 'crawl_strdatetime'

        cursor.execute(f"SELECT COUNT(*) FROM hhp_retail_com WHERE DATE({hhp_date_col}::timestamp) = %s", (target_date,))
        hhp_total_records = cursor.fetchone()[0] or 0

        hhp_dup_dict = get_duplicate_count('hhp_retail_com', hhp_date_col, hhp_dup_keys, target_date, use_period=True, group_by_col='account_name')

        # 중복검증 정상처리 건수 차감
        hhp_dup_normal = {}
        try:
            cursor.execute("""
                SELECT retailer, COUNT(*) FROM monitoring_corrections
                WHERE table_name = 'hhp_retail_com' AND crawl_date = %s
                  AND correction_type = 'duplicate_check' AND status = 'normal'
                GROUP BY retailer
            """, (str(target_date),))
            for nr in cursor.fetchall():
                hhp_dup_normal[nr[0]] = nr[1]
        except Exception:
            pass

        hhp_dup_retailers = []
        hhp_dup_total = 0
        for retailer_name in retailer_list:
            dup_count = max(0, hhp_dup_dict.get(retailer_name, 0) - hhp_dup_normal.get(retailer_name, 0))
            hhp_dup_retailers.append({
                'retailer': retailer_name,
                'duplicate_groups': dup_count,
                'status': get_status(dup_count)
            })
            hhp_dup_total += dup_count

        anomaly_validation['tables'].append({
            'table': 'hhp_retail',
            'table_name': 'HHP Retail',
            'total_records': hhp_total_records,
            'total_issues': hhp_dup_total,
            'duplicate_groups': hhp_dup_total,
            'duplicate_keys': hhp_dup_keys,
            'status': get_status(hhp_dup_total),
            'retailers': hhp_dup_retailers
        })
        total_anomaly_issues += hhp_dup_total

        # YouTube Videos 중복 검증 (CSV 기반)
        ytv_dup_info = get_duplicate_key_columns('youtube_videos')
        ytv_date_col = ytv_dup_info['date_column'] if ytv_dup_info else 'created_at'
        ytv_dup_keys = ytv_dup_info['duplicate_keys'] if ytv_dup_info else ['video_id', 'keyword']

        cursor.execute(f"SELECT COUNT(*) FROM youtube_videos WHERE DATE({ytv_date_col}) = %s", (target_date,))
        ytv_total_records = cursor.fetchone()[0] or 0
        ytv_dup_total = get_duplicate_count('youtube_videos', ytv_date_col, ytv_dup_keys, target_date)

        # YouTube Logs 중복 검증 (CSV 기반 - JOIN 필요)
        ytl_dup_info = get_duplicate_key_columns('youtube_collection_logs')
        ytl_date_col = ytl_dup_info['date_column'] if ytl_dup_info else 'started_at'
        ytl_dup_keys = ytl_dup_info['duplicate_keys'] if ytl_dup_info else ['keyword', 'category']

        cursor.execute(f"SELECT COUNT(*) FROM youtube_collection_logs WHERE DATE({ytl_date_col}) = %s", (target_date,))
        ytl_total_records = cursor.fetchone()[0] or 0

        # YouTube Logs는 youtube_keywords와 JOIN 필요 (keyword, category가 별도 테이블)
        cursor.execute("""
            SELECT COUNT(*) FROM (
                SELECT k.keyword, k.category
                FROM youtube_collection_logs l
                JOIN youtube_keywords k ON l.keyword_id = k.id
                WHERE DATE(l.started_at) = %s
                GROUP BY k.keyword, k.category
                HAVING COUNT(*) > 1
            ) sub
        """, (target_date,))
        ytl_dup_total = cursor.fetchone()[0] or 0

        yt_total_issues = ytl_dup_total + ytv_dup_total
        anomaly_validation['tables'].append({
            'table': 'youtube',
            'table_name': 'YouTube',
            'total_records': ytl_total_records + ytv_total_records,
            'total_issues': yt_total_issues,
            'duplicate_groups': yt_total_issues,
            'status': get_status(yt_total_issues),
            'retailers': [
                {
                    'retailer': 'Logs',
                    'total': ytl_total_records,
                    'duplicate_groups': ytl_dup_total,
                    'duplicate_keys': ytl_dup_keys,
                    'status': get_status(ytl_dup_total)
                },
                {
                    'retailer': 'Videos',
                    'total': ytv_total_records,
                    'duplicate_groups': ytv_dup_total,
                    'duplicate_keys': ytv_dup_keys,
                    'status': get_status(ytv_dup_total)
                }
            ]
        })
        total_anomaly_issues += yt_total_issues

        # Market 중복 검증 (CSV 기반)
        # Market Trend
        mt_dup_info = get_duplicate_key_columns('market_trend')
        mt_date_col = mt_dup_info['date_column'] if mt_dup_info else 'crawl_at_local_time'
        mt_dup_keys = mt_dup_info['duplicate_keys'] if mt_dup_info else ['keyword']

        cursor.execute(f"SELECT COUNT(*) FROM market_trend WHERE DATE({mt_date_col}) = %s", (target_date,))
        market_trend_total = cursor.fetchone()[0] or 0
        market_trend_dup = get_duplicate_count('market_trend', mt_date_col, mt_dup_keys, target_date)

        # Market Product
        mp_dup_info = get_duplicate_key_columns('market_comp_product')
        mp_date_col = mp_dup_info['date_column'] if mp_dup_info else 'created_at'
        mp_dup_keys = mp_dup_info['duplicate_keys'] if mp_dup_info else ['batch_id', 'samsung_series_name', 'comp_brand', 'comp_series_name']

        cursor.execute(f"SELECT COUNT(*) FROM market_comp_product WHERE DATE({mp_date_col}) = %s", (target_date,))
        market_product_total = cursor.fetchone()[0] or 0
        market_product_dup = get_duplicate_count('market_comp_product', mp_date_col, mp_dup_keys, target_date)

        # Market Event
        me_dup_info = get_duplicate_key_columns('market_comp_event')
        me_date_col = me_dup_info['date_column'] if me_dup_info else 'created_at'
        me_dup_keys = me_dup_info['duplicate_keys'] if me_dup_info else ['batch_id', 'comp_brand', 'comp_sku_name']

        cursor.execute(f"SELECT COUNT(*) FROM market_comp_event WHERE DATE({me_date_col}) = %s", (target_date,))
        market_event_total = cursor.fetchone()[0] or 0
        market_event_dup = get_duplicate_count('market_comp_event', me_date_col, me_dup_keys, target_date)

        market_total_dup = market_trend_dup + market_product_dup + market_event_dup
        anomaly_validation['tables'].append({
            'table': 'market',
            'table_name': 'Market',
            'total_records': market_trend_total + market_product_total + market_event_total,
            'total_issues': market_total_dup,
            'duplicate_groups': market_total_dup,
            'status': get_status(market_total_dup),
            'retailers': [
                {
                    'retailer': 'Trend',
                    'total': market_trend_total,
                    'duplicate_groups': market_trend_dup,
                    'duplicate_keys': mt_dup_keys,
                    'status': get_status(market_trend_dup)
                },
                {
                    'retailer': 'Product',
                    'total': market_product_total,
                    'duplicate_groups': market_product_dup,
                    'duplicate_keys': mp_dup_keys,
                    'status': get_status(market_product_dup)
                },
                {
                    'retailer': 'Event',
                    'total': market_event_total,
                    'duplicate_groups': market_event_dup,
                    'duplicate_keys': me_dup_keys,
                    'status': get_status(market_event_dup)
                }
            ]
        })
        total_anomaly_issues += market_total_dup

        anomaly_validation['total_issues'] = total_anomaly_issues
        anomaly_validation['status'] = get_status(total_anomaly_issues)
        results['validation_types'].append(anomaly_validation)

        # Summary 계산
        total_issues = total_null_issues + total_format_issues + total_anomaly_issues
        results['summary'] = {
            'total_issues': total_issues,
            'null_issues': total_null_issues,
            'format_issues': total_format_issues,
            'duplicate_issues': total_anomaly_issues,
            'overall_status': 'OK' if total_issues == 0 else ('WARNING' if total_issues <= 30 else 'CRITICAL')
        }

    except Exception as e:
        results['error'] = log_error(e)
        results['summary']['overall_status'] = 'ERROR'
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

    return JsonResponse(results)


def null_detail(request):
    """NULL 필드 상세 조회 API - category 기반 동적 처리"""
    target_date = parse_date(request.GET.get('date'))
    if target_date is None:
        return JsonResponse({'error': '날짜 형식이 올바르지 않습니다.'}, status=400)
    category = request.GET.get('table', 'tv_retail')
    if category not in get_all_categories():
        return JsonResponse({'error': '잘못된 테이블 파라미터'}, status=400)
    retailer = request.GET.get('retailer')
    try:
        days = max(1, int(request.GET.get('days', 1)))
    except (ValueError, TypeError):
        days = 1

    next_date = target_date + timedelta(days=1)

    # 리테일러 테이블 (account_name 조건 필요)
    retail_categories = ['tv_retail', 'hhp_retail']

    try:
        conn = get_dx_connection()
        cursor = conn.cursor()

        # category에 해당하는 check_names 가져오기
        check_names = get_check_names_by_category(category)
        if not check_names:
            cursor.close()
            conn.close()
            return JsonResponse({'results': [], 'display_config': {}, 'query_config': {}, 'date': str(target_date)})

        # retailer가 있으면 해당 check_name 찾기
        check_name = None
        if retailer:
            # retailer로 check_name 매칭
            retailer_lower = retailer.lower().replace(' ', '_')
            for cn in check_names:
                # tv_retail, hhp_retail: amazon_tv -> Amazon 매칭
                # youtube: youtube_logs -> Logs 매칭
                # market: market_trend -> Trend 매칭
                if category in retail_categories:
                    if cn.startswith(retailer_lower):
                        check_name = cn
                        break
                else:
                    # check_name에서 category 부분 제거하고 비교
                    parts = cn.split('_')
                    if len(parts) > 1:
                        cn_retailer = '_'.join(parts[1:]) if parts[0] == category.split('_')[0] else cn
                    else:
                        cn_retailer = cn
                    if cn_retailer.lower().replace('_', ' ') == retailer.lower() or cn_retailer.lower() == retailer_lower:
                        check_name = cn
                        break

        # check_name이 없으면 첫 번째 사용
        if not check_name:
            check_name = check_names[0]

        # 설정 가져오기
        category_config = get_null_check_config(check_name)
        if not category_config:
            cursor.close()
            conn.close()
            return JsonResponse({'results': [], 'display_config': {}, 'query_config': {}, 'date': str(target_date)})

        actual_table = category_config['table_name']
        date_col = category_config.get('date_column', 'created_at')
        all_null_check_cols = list(category_config['columns'].keys())

        # WHERE 조건 생성
        where_conditions = []
        for col_name in all_null_check_cols:
            where_conditions.append(get_null_check_where_condition(check_name, col_name))
        where_conds = ' OR '.join(where_conditions)

        # 조회할 칼럼 수집
        select_cols_set = {'id', date_col}
        # retail 테이블은 item, account_name, product_url 포함
        if category in retail_categories:
            select_cols_set.update(['account_name', 'item', 'product_url'])
        for col_name in all_null_check_cols:
            select_cols_set.add(col_name)
            select_cols_set.update(get_null_display_columns(check_name, col_name))
            select_cols_set.update(get_null_query_columns(check_name, col_name))
        select_cols = list(select_cols_set)

        # 쿼리 생성
        if category in retail_categories:
            # 리테일러 테이블: account_name 조건 추가
            query = f"""
                SELECT {', '.join(select_cols)}
                FROM {actual_table}
                WHERE {date_col}::timestamp >= %s AND {date_col}::timestamp < %s
                  AND ({where_conds})
            """
            params = [str(target_date), str(next_date)]
            if retailer:
                query += " AND account_name = %s"
                params.append(retailer)
            query += f" ORDER BY account_name, {date_col}"
        else:
            # 그 외 테이블
            query = f"""
                SELECT {', '.join(select_cols)}
                FROM {actual_table}
                WHERE DATE({date_col}) = %s
                  AND ({where_conds})
                ORDER BY {date_col} DESC
            """
            params = [target_date]

        cursor.execute(query, params)
        rows = cursor.fetchall()

        # retail + days > 1: 오류 item 추출 후 N일치 확장 조회
        if category in retail_categories and days > 1 and rows:
            item_idx = select_cols.index('item') if 'item' in select_cols else None
            if item_idx is not None:
                error_items = list(set(r[item_idx] for r in rows if r[item_idx]))
                if error_items:
                    start_date = target_date - timedelta(days=days - 1)
                    placeholders = ', '.join(['%s'] * len(error_items))
                    expand_query = f"""
                        SELECT {', '.join(select_cols)}
                        FROM {actual_table}
                        WHERE {date_col}::timestamp >= %s AND {date_col}::timestamp < %s
                          AND account_name = %s
                          AND item IN ({placeholders})
                        ORDER BY item, {date_col}
                    """
                    expand_params = [str(start_date), str(next_date), retailer] + error_items
                    cursor.execute(expand_query, expand_params)
                    rows = cursor.fetchall()

        # 컬럼 인덱스 매핑
        col_index = {col: idx for idx, col in enumerate(select_cols)}

        # 정상 처리(normal) 건 조회
        normal_set = set()
        normal_reviews = {}
        cursor.execute("""
            SELECT record_id, column_name, memo, created_id, created_at, reason
            FROM monitoring_corrections
            WHERE table_name = %s AND crawl_date = %s
              AND correction_type = 'null_check' AND status = 'normal'
        """, (actual_table, str(target_date)))
        for nr_row in cursor.fetchall():
            nr_key = (nr_row[0], nr_row[1])
            normal_set.add(nr_key)
            normal_reviews[f"{nr_row[0]}_{nr_row[1]}"] = {
                'memo': nr_row[2],
                'created_id': nr_row[3],
                'created_at': nr_row[4].strftime('%Y-%m-%d %H:%M:%S') if nr_row[4] else None,
                'reason': nr_row[5]
            }

        results = []
        for row in rows:
            record_data = {}
            for col_name in select_cols:
                idx = col_index.get(col_name)
                if idx is not None:
                    val = row[idx]
                    if isinstance(val, datetime):
                        record_data[col_name] = val.strftime('%Y-%m-%d %H:%M:%S')
                    else:
                        record_data[col_name] = val

            # null_fields 계산 (정상 처리 건 제외)
            record_id = record_data.get('id')
            null_fields = []
            for col_name in all_null_check_cols:
                if record_id and (record_id, col_name) in normal_set:
                    continue
                idx = col_index.get(col_name)
                if idx is not None:
                    val = row[idx]
                    col_config = category_config['columns'].get(col_name, {})
                    check_type = col_config.get('check_type', 'both')
                    if check_type == 'null':
                        if val is None:
                            null_fields.append(col_name)
                    elif check_type == 'empty':
                        if str(val).strip() == '':
                            null_fields.append(col_name)
                    else:  # both
                        if val is None or str(val).strip() == '':
                            null_fields.append(col_name)

            record_data['null_fields'] = null_fields
            results.append(record_data)

        # display_config, query_config 생성
        display_config = {}
        query_config = {}
        for null_col in all_null_check_cols:
            display_cols = get_null_display_columns(check_name, null_col)
            query_cols = get_null_query_columns(check_name, null_col)
            if display_cols:
                display_config[null_col] = {'select_columns': display_cols}
            if query_cols:
                query_config[null_col] = query_cols

        # 리테일러 전체 수집항목 컬럼 (컬럼 선택 드롭다운용) + 수정 가능 컬럼
        all_retail_cols = []
        editable_cols = []
        if category in retail_categories and retailer:
            product_line = 'tv' if category == 'tv_retail' else 'hhp'
            retail_cols_data = load_retail_columns()
            all_retail_cols = retail_cols_data.get(product_line, {}).get(retailer, [])
            editable_cols = get_editable_columns(product_line, retailer)

        cursor.close()
        conn.close()
        return JsonResponse({
            'results': results,
            'select_cols': all_retail_cols,
            'editable_cols': editable_cols,
            'actual_table': actual_table,
            'display_config': display_config,
            'query_config': query_config,
            'normal_reviews': normal_reviews,
            'date_column': date_col,
            'date': str(target_date)
        })

    except Exception as e:
        return safe_error(e)


def format_detail(request):
    """형식 오류 상세 조회 API"""
    target_date = parse_date(request.GET.get('date'))
    if target_date is None:
        return JsonResponse({'error': '날짜 형식이 올바르지 않습니다.'}, status=400)
    table = request.GET.get('table', 'tv_retail')
    if table not in VALID_TABLES_FORMAT:
        return JsonResponse({'error': '잘못된 테이블 파라미터'}, status=400)
    retailer = request.GET.get('retailer')
    try:
        days = max(1, int(request.GET.get('days', 1)))
    except (ValueError, TypeError):
        days = 1

    try:
        conn = get_dx_connection()
        cursor = conn.cursor()

        results = []
        select_cols = []
        column_names = []
        next_date = target_date + timedelta(days=1)

        # TV Retail 형식 오류 상세 조회 - SQL 조건으로 오류 행 직접 필터링
        if table == 'tv_retail':
            select_cols = ['id', 'item', 'crawl_datetime', 'product_url']
            all_fields = [
                'item', 'page_type', 'product_url', 'main_rank', 'bsr_rank',
                'final_sku_price', 'original_sku_price',
                'count_of_reviews', 'star_rating', 'count_of_star_ratings',
                'detailed_review_content',
                'number_of_units_purchased_past_month', 'available_quantity_for_purchase',
                'sku_popularity', 'retailer_membership_discounts',
                'rank_1', 'rank_2', 'summarized_review_content',
                'savings', 'offer', 'retailer_sku_name_similar', 'recommendation_intent',
                'number_of_ppl_purchased_yesterday', 'number_of_ppl_added_to_carts', 'discount_type'
            ]
            column_names = ['id', 'crawl_datetime'] + all_fields

            # 형식 규칙 → SQL WHERE 조건 변환
            error_where = build_format_error_sql('tv_retail_com', 'TV', retailer)
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"[format_detail] TV error_where SQL: {error_where[:2000]}")

            query = f"""
                SELECT
                    id, crawl_datetime, account_name, {', '.join(all_fields)}
                FROM tv_retail_com
                WHERE crawl_datetime::timestamp >= %s AND crawl_datetime::timestamp < %s
            """
            params = [str(target_date), str(next_date)]
            if retailer:
                query += " AND account_name = %s"
                params.append(retailer)
            query += f" AND ({error_where})"
            query += " ORDER BY account_name, crawl_datetime"

            logger.warning(f"[format_detail] TV full query: {query[:3000]}")
            cursor.execute(query, params)
            for row in cursor.fetchall():
                record_id = row[0]
                crawl_dt = row[1]
                account_name = row[2]
                values = list(row[3:])

                record = {'id': record_id, 'crawl_datetime': str(crawl_dt) if crawl_dt else None}
                for field, value in zip(all_fields, values):
                    record[field] = str(value) if value is not None else None

                # 오류 행 내 개별 필드 오류 식별 (Python 검증, 소수 행만 대상)
                error_fields = []
                error_details = {}
                for field, value in zip(all_fields, values):
                    error = validate_tv_field(field, value, account_name)
                    if error:
                        error_fields.append(field)
                        error_details[field] = {
                            'rule': error.split(':')[0] if ':' in error else error,
                            'reason': error.split(':')[1].strip() if ':' in error else error
                        }

                if error_fields:
                    record['error_fields'] = error_fields
                    record['error_details'] = error_details
                    results.append(record)

        # HHP Retail 형식 오류 상세 조회 - SQL 조건으로 오류 행 직접 필터링
        elif table == 'hhp_retail':
            select_cols = ['id', 'item', 'crawl_datetime', 'product_url']
            cursor.execute("SELECT DISTINCT item FROM hhp_item_mst")
            hhp_valid_items = set(row[0] for row in cursor.fetchall())

            hhp_fields = [
                'item', 'page_type', 'product_url', 'main_rank', 'bsr_rank', 'trend_rank',
                'final_sku_price', 'original_sku_price',
                'count_of_reviews', 'star_rating', 'count_of_star_ratings',
                'detailed_review_content', 'trade_in', 'sku_status',
                'number_of_units_purchased_past_month', 'available_quantity_for_purchase',
                'sku_popularity', 'retailer_membership_discounts',
                'rank_1', 'rank_2', 'summarized_review_content',
                'savings', 'offer', 'retailer_sku_name_similar', 'recommendation_intent',
                'number_of_ppl_purchased_yesterday', 'number_of_ppl_added_to_carts', 'discount_type'
            ]
            column_names = ['id', 'crawl_datetime'] + hhp_fields

            # 형식 규칙 → SQL WHERE 조건 변환 + item 참조 무결성 체크
            error_where = build_format_error_sql('hhp_retail_com', 'HHP', retailer)
            item_check = "item IS NOT NULL AND TRIM(item::text) != '' AND item NOT IN (SELECT DISTINCT item FROM hhp_item_mst)"
            full_error_where = f"({error_where}) OR ({item_check})"

            query = f"""
                SELECT
                    id, crawl_strdatetime, account_name, {', '.join(hhp_fields)}
                FROM hhp_retail_com
                WHERE crawl_strdatetime::timestamp >= %s AND crawl_strdatetime::timestamp < %s
            """
            params = [str(target_date), str(next_date)]
            if retailer:
                query += " AND account_name = %s"
                params.append(retailer)
            query += f" AND ({full_error_where})"
            query += " ORDER BY account_name, crawl_strdatetime"

            cursor.execute(query, params)
            for row in cursor.fetchall():
                record_id = row[0]
                crawl_dt = row[1]
                account_name = row[2]
                values = list(row[3:])

                record = {'id': record_id, 'crawl_datetime': str(crawl_dt) if crawl_dt else None}
                for field, value in zip(hhp_fields, values):
                    record[field] = str(value) if value is not None else None

                # 오류 행 내 개별 필드 오류 식별 (Python 검증, 소수 행만 대상)
                error_fields = []
                error_details = {}
                for field, value in zip(hhp_fields, values):
                    error = validate_hhp_field(field, value, account_name)
                    if error:
                        error_fields.append(field)
                        error_details[field] = {
                            'rule': error.split(':')[0] if ':' in error else error,
                            'reason': error.split(':')[1].strip() if ':' in error else error
                        }

                item = values[0]  # hhp_fields[0] = 'item'
                if item and item not in hhp_valid_items:
                    error_fields.append('item')
                    error_details['item'] = {
                        'rule': '참조 무결성',
                        'reason': '마스터 테이블에 등록되지 않은 item'
                    }

                if error_fields:
                    record['error_fields'] = error_fields
                    record['error_details'] = error_details
                    results.append(record)

        # YouTube 형식 오류 상세 조회 — 규칙 테이블 기반
        elif table == 'youtube_logs' or (table == 'youtube' and retailer == 'Logs'):
            db_table = 'youtube_collection_logs'
            account_name = 'Logs'
            date_col = 'started_at'
            all_fields = ['keyword', 'status', 'videos_collected', 'comments_collected', 'started_at']
            column_names = ['id'] + all_fields

            error_where = build_format_error_sql(db_table, 'ALL', account_name)
            field_checks = build_per_field_error_sql(db_table, 'ALL', account_name)

            if error_where != 'FALSE':
                case_cols = [f"CASE WHEN {fc['cond']} THEN 1 ELSE 0 END" for fc in field_checks]
                select_parts = 'id, ' + ', '.join(all_fields + case_cols) if case_cols else 'id, ' + ', '.join(all_fields)

                cursor.execute(f"""
                    SELECT {select_parts}
                    FROM {db_table}
                    WHERE DATE({date_col}) = %s AND ({error_where})
                    ORDER BY {date_col} DESC
                """, (target_date,))
                for row in cursor.fetchall():
                    record = {'id': row[0]}
                    values = list(row[1:len(all_fields)+1])
                    err_flags = list(row[len(all_fields)+1:])

                    for field, value in zip(all_fields, values):
                        record[field] = str(value) if value is not None else None

                    error_fields = []
                    error_details = {}
                    for i, fc in enumerate(field_checks):
                        if i < len(err_flags) and err_flags[i] == 1:
                            error_fields.append(fc['field'])
                            error_details[fc['field']] = {
                                'rule': fc['field'],
                                'reason': fc['error'] or f"{fc['field']} 형식 오류"
                            }

                    record['error_fields'] = error_fields
                    record['error_details'] = error_details
                    results.append(record)

        elif table == 'youtube_videos' or (table == 'youtube' and retailer == 'Videos'):
            db_table = 'youtube_videos'
            account_name = 'Videos'
            date_col = 'created_at'
            all_fields = ['video_id', 'keyword', 'channel_custom_url', 'category',
                          'engagement_rate', 'product_sentiment_score', 'published_at', 'created_at',
                          'channel_subscriber_count', 'channel_video_count', 'view_count', 'like_count', 'comment_count']
            column_names = ['id'] + all_fields

            error_where = build_format_error_sql(db_table, 'ALL', account_name)
            field_checks = build_per_field_error_sql(db_table, 'ALL', account_name)

            if error_where != 'FALSE':
                case_cols = [f"CASE WHEN {fc['cond']} THEN 1 ELSE 0 END" for fc in field_checks]
                select_parts = ', '.join(all_fields + case_cols) if case_cols else ', '.join(all_fields)

                cursor.execute(f"""
                    SELECT {select_parts}
                    FROM {db_table}
                    WHERE DATE({date_col}) = %s AND ({error_where})
                    ORDER BY {date_col} DESC
                """, (target_date,))
                for row in cursor.fetchall():
                    values = list(row[:len(all_fields)])
                    err_flags = list(row[len(all_fields):])

                    record = {'id': values[0]}  # video_id as id
                    for field, value in zip(all_fields, values):
                        if field in ('engagement_rate', 'product_sentiment_score'):
                            record[field] = float(value) if value is not None else None
                        elif field in ('published_at', 'created_at'):
                            record[field] = str(value)[:19] if value else None
                        else:
                            record[field] = str(value) if value is not None else None

                    error_fields = []
                    error_details = {}
                    for i, fc in enumerate(field_checks):
                        if i < len(err_flags) and err_flags[i] == 1:
                            error_fields.append(fc['field'])
                            error_details[fc['field']] = {
                                'rule': fc['field'],
                                'reason': fc['error'] or f"{fc['field']} 형식 오류"
                            }

                    record['error_fields'] = error_fields
                    record['error_details'] = error_details
                    results.append(record)

        elif table == 'youtube_comments' or (table == 'youtube' and retailer == 'Comments'):
            db_table = 'youtube_comments'
            account_name = 'Comments'
            date_col = 'created_at'
            all_fields = ['video_id', 'comment_type', 'parent_comment_id', 'like_count', 'reply_count', 'published_at', 'created_at']
            column_names = ['id'] + all_fields

            error_where = build_format_error_sql(db_table, 'ALL', account_name)
            field_checks = build_per_field_error_sql(db_table, 'ALL', account_name)

            if error_where != 'FALSE':
                case_cols = [f"CASE WHEN {fc['cond']} THEN 1 ELSE 0 END" for fc in field_checks]
                select_parts = 'comment_id, ' + ', '.join(all_fields + case_cols) if case_cols else 'comment_id, ' + ', '.join(all_fields)

                cursor.execute(f"""
                    SELECT {select_parts}
                    FROM {db_table}
                    WHERE DATE({date_col}) = %s AND ({error_where})
                    ORDER BY comment_id DESC
                """, (target_date,))
                for row in cursor.fetchall():
                    record = {'id': row[0]}
                    values = list(row[1:len(all_fields)+1])
                    err_flags = list(row[len(all_fields)+1:])

                    for field, value in zip(all_fields, values):
                        if field in ('published_at', 'created_at'):
                            record[field] = str(value)[:19] if value else None
                        else:
                            record[field] = str(value) if value is not None else None

                    error_fields = []
                    error_details = {}
                    for i, fc in enumerate(field_checks):
                        if i < len(err_flags) and err_flags[i] == 1:
                            error_fields.append(fc['field'])
                            error_details[fc['field']] = {
                                'rule': fc['field'],
                                'reason': fc['error'] or f"{fc['field']} 형식 오류"
                            }

                    record['error_fields'] = error_fields
                    record['error_details'] = error_details
                    results.append(record)

        # Market 형식 오류 상세 조회 — 규칙 테이블 기반
        elif table == 'market' and retailer in ('Trend', 'Comp Product', 'Comp Event', 'Forecast'):
            market_config = {
                'Trend': ('market_trend', 'crawl_at_local_time', ['keyword', 'total_article_number', 'calendar_week', 'crawl_at_local_time']),
                'Comp Product': ('market_comp_product', 'created_at', ['samsung_series_name', 'comp_brand', 'calender_week', 'category', 'created_at']),
                'Comp Event': ('market_comp_event', 'created_at', ['comp_brand', 'comp_sku_name', 'calender_week', 'category', 'created_at']),
                'Forecast': ('openai_forecast_results', 'crawled_at', ['product_name', 'event', 'metric_type', 'event_offset', 'event_value', 'week', 'crawled_at']),
            }
            db_table, date_col, all_fields = market_config[retailer]
            account_name = retailer
            column_names = ['id'] + all_fields

            error_where = build_format_error_sql(db_table, 'ALL', account_name)
            field_checks = build_per_field_error_sql(db_table, 'ALL', account_name)

            if error_where != 'FALSE':
                case_cols = [f"CASE WHEN {fc['cond']} THEN 1 ELSE 0 END" for fc in field_checks]
                select_parts = 'id, ' + ', '.join(all_fields + case_cols) if case_cols else 'id, ' + ', '.join(all_fields)

                cursor.execute(f"""
                    SELECT {select_parts}
                    FROM {db_table}
                    WHERE DATE({date_col}) = %s AND ({error_where})
                    ORDER BY {date_col} DESC
                """, (target_date,))
                for row in cursor.fetchall():
                    record = {'id': row[0]}
                    values = list(row[1:len(all_fields)+1])
                    err_flags = list(row[len(all_fields)+1:])

                    for field, value in zip(all_fields, values):
                        record[field] = str(value) if value is not None else None

                    error_fields = []
                    error_details = {}
                    for i, fc in enumerate(field_checks):
                        if i < len(err_flags) and err_flags[i] == 1:
                            error_fields.append(fc['field'])
                            error_details[fc['field']] = {
                                'rule': fc['field'],
                                'reason': fc['error'] or f"{fc['field']} 형식 오류"
                            }

                    record['error_fields'] = error_fields
                    record['error_details'] = error_details
                    results.append(record)

        # retail + days > 1: 오류 item으로 N일치 확장 재조회
        if days > 1 and table in ('tv_retail', 'hhp_retail') and results:
            error_items = list(set(r['item'] for r in results if r.get('item')))
            if error_items:
                start_date = target_date - timedelta(days=days - 1)
                placeholders = ', '.join(['%s'] * len(error_items))
                results = []

                if table == 'tv_retail':
                    query = f"""
                        SELECT
                            id, crawl_datetime, account_name, item, page_type, product_url,
                            main_rank, bsr_rank, final_sku_price, original_sku_price,
                            count_of_reviews, star_rating, count_of_star_ratings,
                            detailed_review_content,
                            number_of_units_purchased_past_month, available_quantity_for_purchase,
                            sku_popularity, retailer_membership_discounts,
                            rank_1, rank_2, summarized_review_content,
                            savings, offer, retailer_sku_name_similar, recommendation_intent,
                            number_of_ppl_purchased_yesterday, number_of_ppl_added_to_carts, discount_type
                        FROM tv_retail_com
                        WHERE crawl_datetime::timestamp >= %s AND crawl_datetime::timestamp < %s
                          AND account_name = %s AND item IN ({placeholders})
                        ORDER BY item, crawl_datetime
                    """
                    expand_params = [str(start_date), str(next_date), retailer] + error_items
                    cursor.execute(query, expand_params)
                    rows = cursor.fetchall()
                    all_fields = [
                        'item', 'page_type', 'product_url', 'main_rank', 'bsr_rank',
                        'final_sku_price', 'original_sku_price',
                        'count_of_reviews', 'star_rating', 'count_of_star_ratings',
                        'detailed_review_content',
                        'number_of_units_purchased_past_month', 'available_quantity_for_purchase',
                        'sku_popularity', 'retailer_membership_discounts',
                        'rank_1', 'rank_2', 'summarized_review_content',
                        'savings', 'offer', 'retailer_sku_name_similar', 'recommendation_intent',
                        'number_of_ppl_purchased_yesterday', 'number_of_ppl_added_to_carts', 'discount_type'
                    ]
                    for row in rows:
                        record_id = row[0]
                        crawl_dt = row[1]
                        account_name = row[2]
                        values = list(row[3:])

                        record = {'id': record_id, 'crawl_datetime': str(crawl_dt) if crawl_dt else None}
                        for field, value in zip(all_fields, values):
                            record[field] = str(value) if value is not None else None

                        error_fields = []
                        error_details = {}
                        for field, value in zip(all_fields, values):
                            error = validate_tv_field(field, value, account_name)
                            if error:
                                error_fields.append(field)
                                error_details[field] = {
                                    'rule': error.split(':')[0] if ':' in error else error,
                                    'reason': error.split(':')[1].strip() if ':' in error else error
                                }
                        record['error_fields'] = error_fields
                        record['error_details'] = error_details
                        results.append(record)

                elif table == 'hhp_retail':
                    query = f"""
                        SELECT
                            id, crawl_strdatetime, account_name, item, page_type, product_url,
                            main_rank, bsr_rank, trend_rank, final_sku_price, original_sku_price,
                            count_of_reviews, star_rating, count_of_star_ratings,
                            detailed_review_content, trade_in, sku_status,
                            number_of_units_purchased_past_month, available_quantity_for_purchase,
                            sku_popularity, retailer_membership_discounts,
                            rank_1, rank_2, summarized_review_content,
                            savings, offer, retailer_sku_name_similar, recommendation_intent,
                            number_of_ppl_purchased_yesterday, number_of_ppl_added_to_carts, discount_type
                        FROM hhp_retail_com
                        WHERE crawl_strdatetime::timestamp >= %s AND crawl_strdatetime::timestamp < %s
                          AND account_name = %s AND item IN ({placeholders})
                        ORDER BY item, crawl_strdatetime
                    """
                    expand_params = [str(start_date), str(next_date), retailer] + error_items
                    cursor.execute(query, expand_params)
                    rows = cursor.fetchall()
                    hhp_fields = [
                        'item', 'page_type', 'product_url', 'main_rank', 'bsr_rank', 'trend_rank',
                        'final_sku_price', 'original_sku_price',
                        'count_of_reviews', 'star_rating', 'count_of_star_ratings',
                        'detailed_review_content', 'trade_in', 'sku_status',
                        'number_of_units_purchased_past_month', 'available_quantity_for_purchase',
                        'sku_popularity', 'retailer_membership_discounts',
                        'rank_1', 'rank_2', 'summarized_review_content',
                        'savings', 'offer', 'retailer_sku_name_similar', 'recommendation_intent',
                        'number_of_ppl_purchased_yesterday', 'number_of_ppl_added_to_carts', 'discount_type'
                    ]
                    for row in rows:
                        record_id = row[0]
                        crawl_dt = row[1]
                        account_name = row[2]
                        values = list(row[3:])

                        record = {'id': record_id, 'crawl_datetime': str(crawl_dt) if crawl_dt else None}
                        for field, value in zip(hhp_fields, values):
                            record[field] = str(value) if value is not None else None

                        error_fields = []
                        error_details = {}
                        for field, value in zip(hhp_fields, values):
                            error = validate_hhp_field(field, value, account_name)
                            if error:
                                error_fields.append(field)
                                error_details[field] = {
                                    'rule': error.split(':')[0] if ':' in error else error,
                                    'reason': error.split(':')[1].strip() if ':' in error else error
                                }
                        record['error_fields'] = error_fields
                        record['error_details'] = error_details
                        results.append(record)

        # 수정 가능 컬럼 + actual_table 설정
        editable_cols = []
        actual_table = ''
        if table in ('tv_retail', 'hhp_retail') and retailer:
            product_line = 'tv' if table == 'tv_retail' else 'hhp'
            actual_table = 'tv_retail_com' if table == 'tv_retail' else 'hhp_retail_com'
            editable_cols = get_editable_columns(product_line, retailer)
        elif table in ('youtube_logs',) or (table == 'youtube' and retailer == 'Logs'):
            actual_table = 'youtube_collection_logs'
        elif table in ('youtube_videos',) or (table == 'youtube' and retailer == 'Videos'):
            actual_table = 'youtube_videos'
        elif table in ('youtube_comments',) or (table == 'youtube' and retailer == 'Comments'):
            actual_table = 'youtube_comments'
        elif table == 'market' and retailer:
            market_table_map = {
                'Trend': 'market_trend',
                'Comp Product': 'market_comp_product',
                'Comp Event': 'market_comp_event',
                'Forecast': 'openai_forecast_results',
            }
            actual_table = market_table_map.get(retailer, '')

        # 형식 검증 정상 처리 건 조회
        normal_reviews = {}
        if actual_table:
            cursor.execute("""
                SELECT record_id, column_name, memo, created_id, created_at, reason
                FROM monitoring_corrections
                WHERE table_name = %s AND crawl_date = %s
                  AND correction_type = 'format_check' AND status = 'normal'
            """, (actual_table, str(target_date)))
            for nr_row in cursor.fetchall():
                normal_reviews[f"{nr_row[0]}_{nr_row[1]}"] = {
                    'memo': nr_row[2],
                    'created_id': nr_row[3],
                    'created_at': nr_row[4].strftime('%Y-%m-%d %H:%M:%S') if nr_row[4] else None,
                    'reason': nr_row[5]
                }

        # 정상 처리된 필드는 error_fields에서 제외 (null_detail의 normal_set 패턴)
        if normal_reviews:
            normal_set = set(normal_reviews.keys())
            for record in results:
                if 'error_fields' in record:
                    record_id = record.get('id')
                    record['error_fields'] = [
                        f for f in record['error_fields']
                        if f"{record_id}_{f}" not in normal_set
                    ]

        cursor.close()
        conn.close()

        return JsonResponse({
            'date': str(target_date),
            'table': table,
            'retailer': retailer,
            'column_names': column_names,
            'editable_cols': editable_cols,
            'actual_table': actual_table,
            'normal_reviews': normal_reviews,
            'results': results
        })

    except Exception as e:
        return safe_error(e)


def anomaly_detail(request):
    """중복 검증 상세 조회 API - 리테일러별, 시간대별 중복 상세"""
    target_date = parse_date(request.GET.get('date'))
    if target_date is None:
        return JsonResponse({'error': '날짜 형식이 올바르지 않습니다.'}, status=400)
    table = request.GET.get('table', 'tv_retail')
    if table not in VALID_TABLES_ANOMALY:
        return JsonResponse({'error': '잘못된 테이블 파라미터'}, status=400)
    retailer = request.GET.get('retailer', '')
    try:
        days = max(1, int(request.GET.get('days', 1)))
    except (ValueError, TypeError):
        days = 1
    try:
        page = max(1, int(request.GET.get('page', 1)))
        page_size = min(int(request.GET.get('page_size', 50)), 200)
    except (ValueError, TypeError):
        return JsonResponse({'error': '잘못된 페이지 파라미터'}, status=400)

    offset = (page - 1) * page_size

    try:
        conn = get_dx_connection()
        cursor = conn.cursor()

        duplicates = []
        total_groups = 0
        select_cols = {'group': [], 'record': []}

        if table == 'tv_retail':
            select_cols = {'group': ['item', 'retailer', 'period', 'dup_count', 'reason'], 'record': ['id', 'product_url', 'crawl_datetime', 'page_type', 'main_rank', 'bsr_rank']}
            # 전체 그룹 수
            cursor.execute("""
                SELECT COUNT(*) FROM (
                    SELECT item, account_name,
                           CASE WHEN EXTRACT(HOUR FROM crawl_datetime::timestamp) < 12 THEN '오전' ELSE '오후' END as period
                    FROM tv_retail_com
                    WHERE DATE(crawl_datetime::timestamp) = %s
                      AND (%s = '' OR account_name = %s)
                    GROUP BY item, account_name, period
                    HAVING COUNT(*) > 1
                ) sub
            """, (target_date, retailer, retailer))
            total_groups = cursor.fetchone()[0]

            # 중복 그룹 찾기: item + 시간대 (오전/오후 각각 1건만 있어야 정상)
            # page_type은 무시 - main과 bsr에서 같은 item이 수집되는 건 정상
            cursor.execute("""
                WITH duplicate_groups AS (
                    SELECT item, account_name,
                           CASE WHEN EXTRACT(HOUR FROM crawl_datetime::timestamp) < 12 THEN '오전' ELSE '오후' END as period,
                           COUNT(*) as dup_count
                    FROM tv_retail_com
                    WHERE DATE(crawl_datetime::timestamp) = %s
                      AND (%s = '' OR account_name = %s)
                    GROUP BY item, account_name, period
                    HAVING COUNT(*) > 1
                    ORDER BY COUNT(*) DESC, item, period
                    LIMIT %s OFFSET %s
                )
                SELECT d.item, d.account_name, d.period, d.dup_count,
                       t.id, t.product_url, t.crawl_datetime, t.page_type, t.main_rank, t.bsr_rank
                FROM duplicate_groups d
                JOIN tv_retail_com t ON t.item IS NOT DISTINCT FROM d.item
                    AND t.account_name = d.account_name
                    AND DATE(t.crawl_datetime::timestamp) = %s
                    AND CASE WHEN EXTRACT(HOUR FROM t.crawl_datetime::timestamp) < 12 THEN '오전' ELSE '오후' END = d.period
                ORDER BY d.dup_count DESC, d.item, d.period, t.crawl_datetime
            """, (target_date, retailer, retailer, page_size, offset, target_date))

            rows = cursor.fetchall()

            # 중복 그룹별로 묶기
            dup_groups = {}
            for row in rows:
                key = (row[0], row[1], row[2])  # item, account_name, period
                if key not in dup_groups:
                    dup_groups[key] = {
                        'item': row[0],
                        'retailer': row[1],
                        'period': row[2],
                        'dup_count': row[3],
                        'reason': f'동일 item이 {row[2]}에 {row[3]}건 수집됨',
                        'records': []
                    }
                dup_groups[key]['records'].append({
                    'id': row[4],
                    'product_url': row[5],
                    'crawl_datetime': str(row[6]) if row[6] else None,
                    'page_type': row[7],
                    'main_rank': row[8],
                    'bsr_rank': row[9]
                })

            duplicates = list(dup_groups.values())

        elif table == 'hhp_retail':
            select_cols = {'group': ['item', 'retailer', 'period', 'dup_count', 'reason'], 'record': ['id', 'product_url', 'crawl_datetime', 'page_type', 'rank']}
            cursor.execute("""
                SELECT COUNT(*) FROM (
                    SELECT item, account_name,
                           CASE WHEN EXTRACT(HOUR FROM crawl_strdatetime::timestamp) < 12 THEN '오전' ELSE '오후' END as period
                    FROM hhp_retail_com
                    WHERE DATE(crawl_strdatetime::timestamp) = %s
                      AND (%s = '' OR account_name = %s)
                    GROUP BY item, account_name, period
                    HAVING COUNT(*) > 1
                ) sub
            """, (target_date, retailer, retailer))
            total_groups = cursor.fetchone()[0]

            # 중복 그룹 찾기: item + 시간대 (오전/오후 각각 1건만 있어야 정상)
            # trend_rank는 Bestbuy만 있음
            cursor.execute("""
                WITH duplicate_groups AS (
                    SELECT item, account_name,
                           CASE WHEN EXTRACT(HOUR FROM crawl_strdatetime::timestamp) < 12 THEN '오전' ELSE '오후' END as period,
                           COUNT(*) as dup_count
                    FROM hhp_retail_com
                    WHERE DATE(crawl_strdatetime::timestamp) = %s
                      AND (%s = '' OR account_name = %s)
                    GROUP BY item, account_name, period
                    HAVING COUNT(*) > 1
                    ORDER BY COUNT(*) DESC, item, period
                    LIMIT %s OFFSET %s
                )
                SELECT d.item, d.account_name, d.period, d.dup_count,
                       h.id, h.product_url, h.crawl_strdatetime, h.page_type, h.main_rank, h.bsr_rank, h.trend_rank
                FROM duplicate_groups d
                JOIN hhp_retail_com h ON h.item IS NOT DISTINCT FROM d.item
                    AND h.account_name = d.account_name
                    AND DATE(h.crawl_strdatetime::timestamp) = %s
                    AND CASE WHEN EXTRACT(HOUR FROM h.crawl_strdatetime::timestamp) < 12 THEN '오전' ELSE '오후' END = d.period
                ORDER BY d.dup_count DESC, d.item, d.period, h.crawl_strdatetime
            """, (target_date, retailer, retailer, page_size, offset, target_date))

            rows = cursor.fetchall()

            dup_groups = {}
            for row in rows:
                key = (row[0], row[1], row[2])  # item, account_name, period
                if key not in dup_groups:
                    dup_groups[key] = {
                        'item': row[0],
                        'retailer': row[1],
                        'period': row[2],
                        'dup_count': row[3],
                        'reason': f'동일 item이 {row[2]}에 {row[3]}건 수집됨',
                        'records': []
                    }
                page_type = row[7]
                # page_type에 따라 해당 rank 선택
                if page_type == 'trend':
                    rank = row[10]  # trend_rank (Bestbuy만)
                elif page_type == 'main':
                    rank = row[8]   # main_rank
                elif page_type == 'bsr':
                    rank = row[9]   # bsr_rank
                else:
                    rank = row[8] or row[9]  # fallback
                dup_groups[key]['records'].append({
                    'id': row[4],
                    'product_url': row[5],
                    'crawl_datetime': str(row[6]) if row[6] else None,
                    'page_type': page_type,
                    'rank': rank
                })

            duplicates = list(dup_groups.values())

        elif table == 'youtube_videos':
            select_cols = {'group': ['video_id', 'keyword', 'dup_count', 'reason'], 'record': ['id', 'title', 'created_at']}
            cursor.execute("""
                SELECT COUNT(*) FROM (
                    SELECT video_id, keyword
                    FROM youtube_videos
                    WHERE DATE(created_at) = %s
                    GROUP BY video_id, keyword
                    HAVING COUNT(*) > 1
                ) sub
            """, (target_date,))
            total_groups = cursor.fetchone()[0]

            # YouTube Videos 중복 그룹 찾기: video_id + keyword
            cursor.execute("""
                WITH duplicate_groups AS (
                    SELECT video_id, keyword, COUNT(*) as dup_count
                    FROM youtube_videos
                    WHERE DATE(created_at) = %s
                    GROUP BY video_id, keyword
                    HAVING COUNT(*) > 1
                    ORDER BY COUNT(*) DESC, video_id, keyword
                    LIMIT %s OFFSET %s
                )
                SELECT d.video_id, d.keyword, d.dup_count,
                       y.id, y.title, y.created_at
                FROM duplicate_groups d
                JOIN youtube_videos y ON y.video_id = d.video_id
                    AND y.keyword = d.keyword
                    AND DATE(y.created_at) = %s
                ORDER BY d.dup_count DESC, d.video_id, d.keyword, y.created_at
            """, (target_date, page_size, offset, target_date))

            rows = cursor.fetchall()

            dup_groups = {}
            for row in rows:
                key = (row[0], row[1])  # video_id, keyword
                if key not in dup_groups:
                    dup_groups[key] = {
                        'video_id': row[0],
                        'keyword': row[1],
                        'dup_count': row[2],
                        'reason': f'동일 video_id+keyword가 {row[2]}건 수집됨',
                        'records': []
                    }
                # 제목 50자 제한
                title = row[4][:50] + '...' if row[4] and len(row[4]) > 50 else row[4]
                dup_groups[key]['records'].append({
                    'id': row[3],
                    'title': title,
                    'created_at': str(row[5]) if row[5] else None
                })

            duplicates = list(dup_groups.values())

        elif table == 'youtube_logs':
            select_cols = {'group': ['keyword', 'category', 'dup_count', 'reason'], 'record': ['id', 'created_at']}
            cursor.execute("""
                SELECT COUNT(*) FROM (
                    SELECT k.keyword, k.category
                    FROM youtube_collection_logs l
                    JOIN youtube_keywords k ON l.keyword_id = k.id
                    WHERE DATE(l.started_at) = %s
                    GROUP BY k.keyword, k.category
                    HAVING COUNT(*) > 1
                ) sub
            """, (target_date,))
            total_groups = cursor.fetchone()[0]

            # YouTube Logs 중복 그룹 찾기: keyword + category (조인 필요)
            cursor.execute("""
                WITH duplicate_groups AS (
                    SELECT k.keyword, k.category, COUNT(*) as dup_count
                    FROM youtube_collection_logs l
                    JOIN youtube_keywords k ON l.keyword_id = k.id
                    WHERE DATE(l.started_at) = %s
                    GROUP BY k.keyword, k.category
                    HAVING COUNT(*) > 1
                    ORDER BY COUNT(*) DESC, k.keyword, k.category
                    LIMIT %s OFFSET %s
                )
                SELECT d.keyword, d.category, d.dup_count,
                       l.id, l.started_at
                FROM duplicate_groups d
                JOIN youtube_keywords k ON k.keyword = d.keyword AND k.category = d.category
                JOIN youtube_collection_logs l ON l.keyword_id = k.id
                    AND DATE(l.started_at) = %s
                ORDER BY d.dup_count DESC, d.keyword, d.category, l.started_at
            """, (target_date, page_size, offset, target_date))

            rows = cursor.fetchall()

            dup_groups = {}
            for row in rows:
                key = (row[0], row[1])  # keyword, category
                if key not in dup_groups:
                    dup_groups[key] = {
                        'keyword': row[0],
                        'category': row[1],
                        'dup_count': row[2],
                        'reason': f'동일 keyword+category가 {row[2]}건 수집됨',
                        'records': []
                    }
                dup_groups[key]['records'].append({
                    'id': row[3],
                    'created_at': str(row[4]) if row[4] else None
                })

            duplicates = list(dup_groups.values())

        elif table == 'market_trend':
            select_cols = {'group': ['keyword', 'dup_count', 'reason'], 'record': ['id', 'total_article_number', 'created_at']}
            cursor.execute("""
                SELECT COUNT(*) FROM (
                    SELECT keyword
                    FROM market_trend
                    WHERE DATE(crawl_at_local_time) = %s
                    GROUP BY keyword
                    HAVING COUNT(*) > 1
                ) sub
            """, (target_date,))
            total_groups = cursor.fetchone()[0]

            # Market Trend 중복: 같은 날짜에 keyword 중복
            cursor.execute("""
                WITH duplicate_groups AS (
                    SELECT keyword, COUNT(*) as dup_count
                    FROM market_trend
                    WHERE DATE(crawl_at_local_time) = %s
                    GROUP BY keyword
                    HAVING COUNT(*) > 1
                    ORDER BY COUNT(*) DESC, keyword
                    LIMIT %s OFFSET %s
                )
                SELECT d.keyword, d.dup_count,
                       m.id, m.total_article_number, m.crawl_at_local_time
                FROM duplicate_groups d
                JOIN market_trend m ON m.keyword = d.keyword
                    AND DATE(m.crawl_at_local_time) = %s
                ORDER BY d.dup_count DESC, d.keyword, m.crawl_at_local_time
            """, (target_date, page_size, offset, target_date))

            rows = cursor.fetchall()

            dup_groups = {}
            for row in rows:
                key = row[0]  # keyword
                if key not in dup_groups:
                    dup_groups[key] = {
                        'keyword': row[0],
                        'dup_count': row[1],
                        'reason': f'동일 keyword가 {row[1]}건 수집됨',
                        'records': []
                    }
                dup_groups[key]['records'].append({
                    'id': row[2],
                    'total_article_number': row[3],
                    'created_at': str(row[4]) if row[4] else None
                })

            duplicates = list(dup_groups.values())

        elif table == 'market_product':
            select_cols = {'group': ['batch_id', 'samsung_series_name', 'comp_brand', 'comp_series_name', 'dup_count', 'reason'], 'record': ['id', 'created_at']}
            cursor.execute("""
                SELECT COUNT(*) FROM (
                    SELECT batch_id, samsung_series_name, comp_brand, comp_series_name
                    FROM market_comp_product
                    WHERE DATE(created_at) = %s
                    GROUP BY batch_id, samsung_series_name, comp_brand, comp_series_name
                    HAVING COUNT(*) > 1
                ) sub
            """, (target_date,))
            total_groups = cursor.fetchone()[0]

            # Market Product 중복: batch_id + samsung_series_name + comp_brand + comp_series_name
            cursor.execute("""
                WITH duplicate_groups AS (
                    SELECT batch_id, samsung_series_name, comp_brand, comp_series_name, COUNT(*) as dup_count
                    FROM market_comp_product
                    WHERE DATE(created_at) = %s
                    GROUP BY batch_id, samsung_series_name, comp_brand, comp_series_name
                    HAVING COUNT(*) > 1
                    ORDER BY COUNT(*) DESC, batch_id, samsung_series_name
                    LIMIT %s OFFSET %s
                )
                SELECT d.batch_id, d.samsung_series_name, d.comp_brand, d.comp_series_name, d.dup_count,
                       m.id, m.created_at
                FROM duplicate_groups d
                JOIN market_comp_product m ON m.batch_id = d.batch_id
                    AND m.samsung_series_name = d.samsung_series_name
                    AND m.comp_brand = d.comp_brand
                    AND m.comp_series_name = d.comp_series_name
                    AND DATE(m.created_at) = %s
                ORDER BY d.dup_count DESC, d.batch_id, d.samsung_series_name, m.created_at
            """, (target_date, page_size, offset, target_date))

            rows = cursor.fetchall()

            dup_groups = {}
            for row in rows:
                key = (row[0], row[1], row[2], row[3])  # batch_id, samsung_series_name, comp_brand, comp_series_name
                if key not in dup_groups:
                    dup_groups[key] = {
                        'batch_id': row[0],
                        'samsung_series_name': row[1],
                        'comp_brand': row[2],
                        'comp_series_name': row[3],
                        'dup_count': row[4],
                        'reason': f'동일 조합이 {row[4]}건 수집됨',
                        'records': []
                    }
                dup_groups[key]['records'].append({
                    'id': row[5],
                    'created_at': str(row[6]) if row[6] else None
                })

            duplicates = list(dup_groups.values())

        elif table == 'market_event':
            select_cols = {'group': ['batch_id', 'comp_brand', 'comp_sku_name', 'dup_count', 'reason'], 'record': ['id', 'created_at']}
            cursor.execute("""
                SELECT COUNT(*) FROM (
                    SELECT batch_id, comp_brand, comp_sku_name
                    FROM market_comp_event
                    WHERE DATE(created_at) = %s
                    GROUP BY batch_id, comp_brand, comp_sku_name
                    HAVING COUNT(*) > 1
                ) sub
            """, (target_date,))
            total_groups = cursor.fetchone()[0]

            # Market Event 중복: batch_id + comp_brand + comp_sku_name
            cursor.execute("""
                WITH duplicate_groups AS (
                    SELECT batch_id, comp_brand, comp_sku_name, COUNT(*) as dup_count
                    FROM market_comp_event
                    WHERE DATE(created_at) = %s
                    GROUP BY batch_id, comp_brand, comp_sku_name
                    HAVING COUNT(*) > 1
                    ORDER BY COUNT(*) DESC, batch_id, comp_brand
                    LIMIT %s OFFSET %s
                )
                SELECT d.batch_id, d.comp_brand, d.comp_sku_name, d.dup_count,
                       m.id, m.created_at
                FROM duplicate_groups d
                JOIN market_comp_event m ON m.batch_id = d.batch_id
                    AND m.comp_brand = d.comp_brand
                    AND m.comp_sku_name = d.comp_sku_name
                    AND DATE(m.created_at) = %s
                ORDER BY d.dup_count DESC, d.batch_id, d.comp_brand, m.created_at
            """, (target_date, page_size, offset, target_date))

            rows = cursor.fetchall()

            dup_groups = {}
            for row in rows:
                key = (row[0], row[1], row[2])  # batch_id, comp_brand, comp_sku_name
                if key not in dup_groups:
                    dup_groups[key] = {
                        'batch_id': row[0],
                        'comp_brand': row[1],
                        'comp_sku_name': row[2],
                        'dup_count': row[3],
                        'reason': f'동일 조합이 {row[3]}건 수집됨',
                        'records': []
                    }
                dup_groups[key]['records'].append({
                    'id': row[4],
                    'created_at': str(row[5]) if row[5] else None
                })

            duplicates = list(dup_groups.values())

        # 수정 가능 컬럼
        editable_cols = []
        actual_table = ''
        if table in ('tv_retail', 'hhp_retail') and retailer:
            product_line = 'tv' if table == 'tv_retail' else 'hhp'
            actual_table = 'tv_retail_com' if table == 'tv_retail' else 'hhp_retail_com'
            editable_cols = get_editable_columns(product_line, retailer)

        cursor.close()
        conn.close()

        total_pages = (total_groups + page_size - 1) // page_size if total_groups > 0 else 0

        return JsonResponse({
            'date': str(target_date),
            'table': table,
            'retailer': retailer,
            'select_cols': select_cols,
            'editable_cols': editable_cols,
            'actual_table': actual_table,
            'results': {
                'duplicates': duplicates,
                'total_groups': total_groups,
                'page': page,
                'page_size': page_size,
                'total_pages': total_pages
            }
        })

    except Exception as e:
        return safe_error(e)


# ============================================================
# 중복 데이터 정리 (Duplicate Cleanup)
# ============================================================

# 테이블별 중복 키 / 날짜 컬럼 / 오전오후 구분 매핑
_DUP_TABLE_CONFIG = {
    'tv_retail': {
        'actual': 'tv_retail_com',
        'dup_keys': 'item, account_name',
        'date_col': 'crawl_datetime',
        'use_period': True,
        'retailer_col': 'account_name',
    },
    'hhp_retail': {
        'actual': 'hhp_retail_com',
        'dup_keys': 'item, account_name',
        'date_col': 'crawl_strdatetime',
        'use_period': True,
        'retailer_col': 'account_name',
    },
    'youtube_videos': {
        'actual': 'youtube_videos',
        'dup_keys': 'video_id, keyword',
        'date_col': 'created_at',
        'use_period': False,
        'retailer_col': None,
    },
    'youtube_logs': {
        'actual': 'youtube_collection_logs',
        'dup_keys': None,  # JOIN 필요 — 별도 처리
        'date_col': 'started_at',
        'use_period': False,
        'retailer_col': None,
    },
    'market_trend': {
        'actual': 'market_trend',
        'dup_keys': 'keyword',
        'date_col': 'crawl_at_local_time',
        'use_period': False,
        'retailer_col': None,
    },
    'market_product': {
        'actual': 'market_comp_product',
        'dup_keys': 'batch_id, samsung_series_name, comp_brand, comp_series_name',
        'date_col': 'created_at',
        'use_period': False,
        'retailer_col': None,
    },
    'market_event': {
        'actual': 'market_comp_event',
        'dup_keys': 'batch_id, comp_brand, comp_sku_name',
        'date_col': 'created_at',
        'use_period': False,
        'retailer_col': None,
    },
}


def _build_dup_delete_query(table, retailer=''):
    """
    중복 그룹에서 최신 1건만 남기고 삭제할 대상의 id + row_to_json 을 조회하는 쿼리를 생성.
    반환: (sql, params)  — sql에는 %s 플레이스홀더, params는 (target_date,) 기준으로 외부에서 결합
    """
    cfg = _DUP_TABLE_CONFIG.get(table)
    if not cfg:
        return None, None

    actual = cfg['actual']
    date_col = cfg['date_col']
    dup_keys = cfg['dup_keys']
    use_period = cfg['use_period']
    retailer_col = cfg['retailer_col']

    # youtube_logs는 JOIN이 필요하므로 별도 처리
    if table == 'youtube_logs':
        sql = f"""
            SELECT sub.id, row_to_json(sub.*) as record_data FROM (
                SELECT l.*, k.keyword as _kw, k.category as _cat,
                       ROW_NUMBER() OVER (
                           PARTITION BY k.keyword, k.category
                           ORDER BY l.{date_col} DESC
                       ) as rn
                FROM {actual} l
                JOIN youtube_keywords k ON l.keyword_id = k.id
                WHERE DATE(l.{date_col}) = %s
            ) sub
            WHERE sub.rn > 1
        """
        return sql, None  # params: (target_date,)

    # 오전/오후 구분이 필요한 경우
    period_expr = ''
    partition_extra = ''
    if use_period:
        period_expr = f"CASE WHEN EXTRACT(HOUR FROM {date_col}::timestamp) < 12 THEN 'AM' ELSE 'PM' END"
        partition_extra = f', {period_expr}'

    # 리테일러 필터
    retailer_where = ''
    if retailer_col and retailer:
        retailer_where = f"AND {retailer_col} = %s"

    sql = f"""
        SELECT sub.id, sub.record_data FROM (
            SELECT t.id, row_to_json(t.*) as record_data,
                   ROW_NUMBER() OVER (
                       PARTITION BY {dup_keys}{partition_extra}
                       ORDER BY {date_col} DESC
                   ) as rn
            FROM {actual} t
            WHERE DATE({date_col}::timestamp) = %s
              {retailer_where}
        ) sub
        WHERE sub.rn > 1
    """
    return sql, retailer_where


def duplicate_cleanup(request):
    """
    중복 데이터 정리 API
    POST → 체크박스로 선택한 id 목록을 백업 후 삭제
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    import json as json_mod
    try:
        data = json_mod.loads(request.body)
    except (json_mod.JSONDecodeError, ValueError):
        return JsonResponse({'error': '잘못된 요청 형식'}, status=400)

    table = data.get('table', '')
    if table not in _DUP_TABLE_CONFIG:
        return JsonResponse({'error': '잘못된 테이블 파라미터'}, status=400)

    ids = data.get('ids', [])
    if not ids:
        return JsonResponse({'error': '삭제할 항목을 선택해주세요.'}, status=400)

    # id를 정수로 변환
    try:
        delete_ids = [int(i) for i in ids]
    except (ValueError, TypeError):
        return JsonResponse({'error': '잘못된 ID 형식'}, status=400)

    cfg = _DUP_TABLE_CONFIG[table]
    actual_table = cfg['actual']
    dup_keys = cfg['dup_keys'] or 'keyword_id'
    use_period = cfg.get('use_period', False)
    date_col = cfg.get('date_col', '')
    backup_table = 'monitoring_duplicate_deletes'

    # 백업용 날짜 (필수 아님)
    target_date = parse_date(data.get('date')) or None

    username = request.user.username if request.user.is_authenticated else ''
    now = datetime.now()

    conn = None
    try:
        conn = get_dx_connection()
        cursor = conn.cursor()

        # 1. 삭제 대상 전체 행 조회 (백업용)
        id_placeholders = ', '.join(['%s'] * len(delete_ids))
        cursor.execute(
            f"SELECT id, row_to_json(t.*) as record_data FROM {actual_table} t WHERE id IN ({id_placeholders})",
            delete_ids
        )
        rows = cursor.fetchall()

        if not rows:
            cursor.close()
            conn.close()
            return JsonResponse({'success': True, 'deleted_count': 0, 'message': '해당 레코드가 존재하지 않습니다.'})

        # item 식별용 컬럼 (dup_keys 첫 번째 키)
        item_col = dup_keys.split(',')[0].strip() if dup_keys else None

        # 2. 백업 INSERT + corrections 이력 저장
        for row in rows:
            record_id = row[0]
            record_data = row[1]

            if isinstance(record_data, str):
                record_json = record_data
                record_dict = json_mod.loads(record_data)
            else:
                record_json = json_mod.dumps(record_data, default=str)
                record_dict = record_data

            # 백업 (dup_group_key: 중복 판별 기준 컬럼명 + period 실제값)
            if use_period:
                date_val = str(record_dict.get(date_col, ''))
                try:
                    hour = int(date_val[11:13])
                    period_label = '오전' if hour < 12 else '오후'
                except (ValueError, IndexError):
                    period_label = ''
                group_key_meta = dup_keys + ', period(' + period_label + ')'
            else:
                group_key_meta = dup_keys
            cursor.execute(f"""
                INSERT INTO {backup_table}
                    (source_table, record_id, record_data, dup_group_key, crawl_date, deleted_by, deleted_at)
                VALUES (%s, %s, %s::jsonb, %s, %s, %s, %s)
            """, (
                actual_table, record_id, record_json,
                group_key_meta, target_date, username, now
            ))

            # corrections 이력
            item_col_name = dup_keys.split(',')[0].strip() if dup_keys else None
            item_value = str(record_dict.get(item_col_name, '')) if item_col_name else ''
            retailer_col = cfg.get('retailer_col')
            retailer_value = str(record_dict.get(retailer_col, '')) if retailer_col else ''
            cursor.execute("""
                INSERT INTO monitoring_corrections
                    (layer, correction_type, table_name, record_id,
                     crawl_date, created_id, created_at, status, memo, retailer, item)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                2, 'duplicate_check', actual_table, record_id,
                target_date, username, now, 'corrected', '중복 삭제', retailer_value,
                item_value or None
            ))

        # 4. DELETE
        fetched_ids = [row[0] for row in rows]
        del_placeholders = ', '.join(['%s'] * len(fetched_ids))
        cursor.execute(f"DELETE FROM {actual_table} WHERE id IN ({del_placeholders})", fetched_ids)

        deleted_count = cursor.rowcount
        conn.commit()
        cursor.close()
        conn.close()

        return JsonResponse({
            'success': True,
            'deleted_count': deleted_count,
            'backup_table': backup_table,
        })

    except Exception as e:
        if conn:
            try:
                conn.rollback()
                conn.close()
            except Exception:
                pass
        return safe_error(e)


# ============================================================
# DS (Samsung DS Retail) APIs
# ============================================================

# DS 모니터링 대상 테이블 정보
DS_MONITORING_TARGETS = [
    ('amazon_price_crawl_tbl_usa_v2', 'Amazon', '미국', 'usa', 'amazon'),
    ('bestbuy_price_crawl_tbl_usa_v2', 'Best Buy', '미국', 'usa', 'bestbuy'),
    ('amazon_price_crawl_tbl_jp_v2', 'Amazon', '일본', 'jp', 'amazon'),
    ('amazon_price_crawl_tbl_ind_v2', 'Amazon', '인도', 'in', 'amazon'),
    ('danawa_price_crawl_tbl_kr_v2', 'Danawa', '한국', 'kr', 'danawa'),
    ('amazon_price_crawl_tbl_uk_v2', 'Amazon', '영국', 'gb', 'amazon'),
    ('currys_price_crawl_tbl_gb_v2', 'Currys', '영국', 'gb', 'currys'),
    ('amazon_price_crawl_tbl_it_v2', 'Amazon', '이탈리아', 'it', 'amazon'),
    ('amazon_price_crawl_tbl_es_v2', 'Amazon', '스페인', 'es', 'amazon'),
    ('amazon_price_crawl_tbl_fr_v2', 'Amazon', '프랑스', 'fr', 'amazon'),
    ('fnac_price_crawl_tbl_fr', 'Fnac', '프랑스', 'fr', 'fnac'),
    ('amazon_price_crawl_tbl_nl', 'Amazon', '네덜란드', 'nl', 'amazon'),
    ('coolblue_price_crawl_tbl_nl_v2', 'Coolblue', '네덜란드', 'nl', 'coolblue'),
    ('amazon_price_crawl_tbl_de_v2', 'Amazon', '독일', 'de', 'amazon'),
    ('mediamarkt_price_crawl_tbl_de_v2', 'MediaMarkt', '독일', 'de', 'mediamarkt'),
    ('xkom_price_crawl_tbl_pl_v2', 'X-Kom', '폴란드', 'pl', 'x-kom'),
    ('centrecom_price_crawl_tbl_au', 'Centre Com', '호주', 'au', 'centrecom'),
]


def ds_layer_stats(request):
    """DS Layer 2 통계 API - NULL/형식/수집률 검증"""
    from apps.common.db import get_ds_connection

    target_date = parse_date(request.GET.get('date'))
    if target_date is None:
        return JsonResponse({'error': '날짜 형식이 올바르지 않습니다.'}, status=400)

    date_str_compact = target_date.strftime('%Y%m%d')
    next_date_compact = (target_date + timedelta(days=1)).strftime('%Y%m%d')
    start_datetime = f"{date_str_compact}0000"
    end_datetime = f"{next_date_compact}0000"

    results = {
        'timestamp': datetime.now().isoformat(),
        'date': str(target_date),
        'layer': 2,
        'name': 'DS 형식/NULL 검수',
        'validation_types': [],
        'summary': {
            'total_issues': 0,
            'null_issues': 0,
            'format_issues': 0,
            'collection_issues': 0,
            'overall_status': 'OK'
        }
    }

    conn = None
    cursor = None
    try:
        conn = get_ds_connection()
        cursor = conn.cursor()

        total_null_issues = 0
        total_format_issues = 0
        total_collection_issues = 0

        # ============================================================
        # 1. NULL 검증
        # ============================================================
        null_validation = {
            'type': 'null',
            'type_name': 'NULL 검증',
            'type_name_en': 'Null Validation',
            'description': '필수 필드(title, imageurl) NULL 검증',
            'icon': '🔍',
            'tables': []
        }

        # 지역별로 그룹화
        region_stats = {}

        for table_name, retailer, region, country, mall_name in DS_MONITORING_TARGETS:
            if region not in region_stats:
                region_stats[region] = {
                    'retailers': [],
                    'total_records': 0,
                    'null_issues': 0
                }

            try:
                # 전체 레코드 수
                cursor.execute(f"""
                    SELECT COUNT(*) FROM (
                        SELECT DISTINCT * FROM samsung_ds_retail_com.{table_name}
                        WHERE crawl_strdatetime >= %s AND crawl_strdatetime < %s
                    ) A
                """, (start_datetime, end_datetime))
                total_count = cursor.fetchone()[0] or 0

                # title NULL 개수
                cursor.execute(f"""
                    SELECT COUNT(*) FROM (
                        SELECT DISTINCT * FROM samsung_ds_retail_com.{table_name}
                        WHERE crawl_strdatetime >= %s AND crawl_strdatetime < %s
                    ) A WHERE (title IS NULL OR title = '')
                """, (start_datetime, end_datetime))
                null_title = cursor.fetchone()[0] or 0

                # imageurl NULL 또는 http로 시작하지 않음
                cursor.execute(f"""
                    SELECT COUNT(*) FROM (
                        SELECT DISTINCT * FROM samsung_ds_retail_com.{table_name}
                        WHERE crawl_strdatetime >= %s AND crawl_strdatetime < %s
                    ) A WHERE (imageurl IS NULL OR imageurl = '' OR imageurl NOT LIKE 'http%%')
                """, (start_datetime, end_datetime))
                null_imageurl = cursor.fetchone()[0] or 0

                null_total = null_title + null_imageurl

                region_stats[region]['retailers'].append({
                    'retailer': retailer,
                    'table': table_name,
                    'country': country,
                    'total': total_count,
                    'null_title': null_title,
                    'null_imageurl': null_imageurl,
                    'null_total': null_total,
                    'status': get_status(null_total)
                })
                region_stats[region]['total_records'] += total_count
                region_stats[region]['null_issues'] += null_total

            except Exception as e:
                region_stats[region]['retailers'].append({
                    'retailer': retailer,
                    'table': table_name,
                    'country': country,
                    'total': 0,
                    'null_title': 0,
                    'null_imageurl': 0,
                    'null_total': 0,
                    'status': 'ERROR',
                    'error': log_error(e)
                })

        # 지역별 NULL 검증 결과 추가
        for region, stats in region_stats.items():
            null_validation['tables'].append({
                'table': region,
                'table_name': f'{region}',
                'total_records': stats['total_records'],
                'total_issues': stats['null_issues'],
                'status': get_status(stats['null_issues']),
                'retailers': stats['retailers']
            })
            total_null_issues += stats['null_issues']

        null_validation['total_issues'] = total_null_issues
        null_validation['status'] = get_status(total_null_issues)
        results['validation_types'].append(null_validation)

        # ============================================================
        # 2. 형식 검증
        # ============================================================
        format_validation = {
            'type': 'format',
            'type_name': '형식 검증',
            'type_name_en': 'Format Validation',
            'description': 'retailprice, ships_from, sold_by 일관성 검증',
            'icon': '📋',
            'tables': []
        }

        format_by_region = {}

        for table_name, retailer, region, country, mall_name in DS_MONITORING_TARGETS:
            if region not in format_by_region:
                format_by_region[region] = {
                    'retailers': [],
                    'total_checked': 0,
                    'format_issues': 0
                }

            try:
                # 전체 레코드 수
                cursor.execute(f"""
                    SELECT COUNT(*) FROM (
                        SELECT DISTINCT * FROM samsung_ds_retail_com.{table_name}
                        WHERE crawl_strdatetime >= %s AND crawl_strdatetime < %s
                    ) A
                """, (start_datetime, end_datetime))
                total_count = cursor.fetchone()[0] or 0

                # retailprice 부분 NULL (title이 있는데 retailprice가 없고 다른 필드는 있는 경우)
                cursor.execute(f"""
                    SELECT COUNT(*) FROM (
                        SELECT DISTINCT * FROM samsung_ds_retail_com.{table_name}
                        WHERE crawl_strdatetime >= %s AND crawl_strdatetime < %s
                    ) A
                    WHERE (retailprice IS NULL OR retailprice = '')
                    AND (title IS NOT NULL AND title != '')
                    AND ((ships_from IS NOT NULL AND ships_from != '') OR (sold_by IS NOT NULL AND sold_by != ''))
                """, (start_datetime, end_datetime))
                format_retailprice = cursor.fetchone()[0] or 0

                # ships_from 부분 NULL
                cursor.execute(f"""
                    SELECT COUNT(*) FROM (
                        SELECT DISTINCT * FROM samsung_ds_retail_com.{table_name}
                        WHERE crawl_strdatetime >= %s AND crawl_strdatetime < %s
                    ) A
                    WHERE (ships_from IS NULL OR ships_from = '')
                    AND (title IS NOT NULL AND title != '')
                    AND ((retailprice IS NOT NULL AND retailprice != '') OR (sold_by IS NOT NULL AND sold_by != ''))
                """, (start_datetime, end_datetime))
                format_ships_from = cursor.fetchone()[0] or 0

                # sold_by 부분 NULL
                cursor.execute(f"""
                    SELECT COUNT(*) FROM (
                        SELECT DISTINCT * FROM samsung_ds_retail_com.{table_name}
                        WHERE crawl_strdatetime >= %s AND crawl_strdatetime < %s
                    ) A
                    WHERE (sold_by IS NULL OR sold_by = '')
                    AND (title IS NOT NULL AND title != '')
                    AND ((retailprice IS NOT NULL AND retailprice != '') OR (ships_from IS NOT NULL AND ships_from != ''))
                """, (start_datetime, end_datetime))
                format_sold_by = cursor.fetchone()[0] or 0

                format_total = format_retailprice + format_ships_from + format_sold_by

                format_by_region[region]['retailers'].append({
                    'retailer': retailer,
                    'table': table_name,
                    'country': country,
                    'total': total_count,
                    'format_retailprice': format_retailprice,
                    'format_ships_from': format_ships_from,
                    'format_sold_by': format_sold_by,
                    'format_total': format_total,
                    'status': get_status(format_total)
                })
                format_by_region[region]['total_checked'] += total_count
                format_by_region[region]['format_issues'] += format_total

            except Exception as e:
                format_by_region[region]['retailers'].append({
                    'retailer': retailer,
                    'table': table_name,
                    'country': country,
                    'total': 0,
                    'format_total': 0,
                    'status': 'ERROR',
                    'error': log_error(e)
                })

        # 지역별 형식 검증 결과 추가
        for region, stats in format_by_region.items():
            format_validation['tables'].append({
                'table': region,
                'table_name': f'{region}',
                'total_checked': stats['total_checked'],
                'total_issues': stats['format_issues'],
                'status': get_status(stats['format_issues']),
                'retailers': stats['retailers']
            })
            total_format_issues += stats['format_issues']

        format_validation['total_issues'] = total_format_issues
        format_validation['status'] = get_status(total_format_issues)
        results['validation_types'].append(format_validation)

        # ============================================================
        # 3. 수집률 검증
        # ============================================================
        collection_validation = {
            'type': 'collection',
            'type_name': '수집률 검증',
            'type_name_en': 'Collection Rate',
            'description': '예상 수집 건수 대비 실제 수집률',
            'icon': '📊',
            'tables': []
        }

        collection_by_region = {}

        for table_name, retailer, region, country, mall_name in DS_MONITORING_TARGETS:
            if region not in collection_by_region:
                collection_by_region[region] = {
                    'retailers': [],
                    'total_expected': 0,
                    'total_actual': 0
                }

            try:
                # 예상 수집 건수
                cursor.execute("""
                    SELECT COUNT(*) FROM samsung_ds_retail_com.samsung_price_tracking_list
                    WHERE country = %s AND mall_name = %s AND is_active = 1
                """, (country, mall_name))
                expected = cursor.fetchone()[0] or 0

                # 실제 수집 건수
                cursor.execute(f"""
                    SELECT COUNT(*) FROM (
                        SELECT DISTINCT * FROM samsung_ds_retail_com.{table_name}
                        WHERE crawl_strdatetime >= %s AND crawl_strdatetime < %s
                    ) A
                """, (start_datetime, end_datetime))
                actual = cursor.fetchone()[0] or 0

                # 수집률 계산
                if expected > 0:
                    rate = round((actual / expected) * 100, 1)
                else:
                    rate = 0

                collection_by_region[region]['retailers'].append({
                    'retailer': retailer,
                    'table': table_name,
                    'country': country,
                    'expected': expected,
                    'actual': actual,
                    'rate': rate,
                    'status': 'OK' if rate >= 90 else ('WARNING' if rate >= 70 else 'CRITICAL')
                })
                collection_by_region[region]['total_expected'] += expected
                collection_by_region[region]['total_actual'] += actual

            except Exception as e:
                collection_by_region[region]['retailers'].append({
                    'retailer': retailer,
                    'table': table_name,
                    'country': country,
                    'expected': 0,
                    'actual': 0,
                    'rate': 0,
                    'status': 'ERROR',
                    'error': log_error(e)
                })

        # 지역별 수집률 결과 추가
        for region, stats in collection_by_region.items():
            if stats['total_expected'] > 0:
                region_rate = round((stats['total_actual'] / stats['total_expected']) * 100, 1)
            else:
                region_rate = 0

            # 90% 미만이면 이슈로 카운트
            issue_count = sum(1 for r in stats['retailers'] if r.get('rate', 0) < 90 and r.get('expected', 0) > 0)

            collection_validation['tables'].append({
                'table': region,
                'table_name': f'{region}',
                'total_expected': stats['total_expected'],
                'total_actual': stats['total_actual'],
                'rate': region_rate,
                'total_issues': issue_count,
                'status': 'OK' if region_rate >= 90 else ('WARNING' if region_rate >= 70 else 'CRITICAL'),
                'retailers': stats['retailers']
            })
            total_collection_issues += issue_count

        collection_validation['total_issues'] = total_collection_issues
        collection_validation['status'] = get_status(total_collection_issues)
        results['validation_types'].append(collection_validation)

        # Summary 계산
        total_issues = total_null_issues + total_format_issues + total_collection_issues
        results['summary'] = {
            'total_issues': total_issues,
            'null_issues': total_null_issues,
            'format_issues': total_format_issues,
            'collection_issues': total_collection_issues,
            'overall_status': 'OK' if total_issues == 0 else ('WARNING' if total_issues <= 30 else 'CRITICAL')
        }

    except Exception as e:
        results['error'] = log_error(e)
        results['summary']['overall_status'] = 'ERROR'
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

    return JsonResponse(results)


def retailer_detail(request):
    """리테일러별 상세 오류 데이터 조회 API"""
    validation_type = request.GET.get('type', 'null')
    table_name = request.GET.get('table', '')
    if table_name not in VALID_TABLES_RETAILER:
        return JsonResponse({'error': '잘못된 테이블 파라미터'}, status=400)
    retailer = request.GET.get('retailer', '')
    target_date = parse_date(request.GET.get('date'))
    if target_date is None:
        return JsonResponse({'error': '날짜 형식이 올바르지 않습니다.'}, status=400)

    results = {
        'type': validation_type,
        'table': table_name,
        'retailer': retailer,
        'date': str(target_date),
        'records': [],
        'total': 0
    }

    try:
        conn = get_dx_connection()
        cursor = conn.cursor()

        # 테이블명 및 날짜 필드 결정
        if table_name == 'TV Retail':
            db_table = 'tv_retail_com'
            date_field = 'crawl_datetime'
            null_fields = ['item', 'screen_size', 'final_sku_price', 'retailer_sku_name',
                          'count_of_reviews', 'star_rating', 'count_of_star_ratings']
        elif table_name == 'HHP Retail':
            db_table = 'hhp_retail_com'
            date_field = 'crawl_strdatetime'
            null_fields = ['item', 'final_sku_price', 'retailer_sku_name',
                          'count_of_reviews', 'star_rating', 'count_of_star_ratings']
        else:
            return JsonResponse({'error': '잘못된 테이블 파라미터'}, status=400)

        if validation_type == 'null':
            # NULL 검증 상세 - 필수값 NULL인 레코드 조회
            null_conditions = ' OR '.join([f"({f} IS NULL OR {f} = '')" for f in null_fields])

            cursor.execute(f"""
                SELECT id, item, {date_field}, product_url,
                       {', '.join([f"CASE WHEN {f} IS NULL OR {f} = '' THEN 1 ELSE 0 END as null_{f}" for f in null_fields])}
                FROM {db_table}
                WHERE DATE({date_field}::timestamp) = %s
                  AND account_name = %s
                  AND ({null_conditions})
                ORDER BY id
                LIMIT 100
            """, (target_date, retailer))

            rows = cursor.fetchall()

            for row in rows:
                record_id = row[0]
                item = row[1]
                crawl_dt = row[2]
                product_url = row[3]

                # NULL인 필드들 찾기
                null_field_list = []
                for i, field in enumerate(null_fields):
                    if row[4 + i] == 1:
                        null_field_list.append(field)

                results['records'].append({
                    'id': record_id,
                    'item': item,
                    'product_url': product_url,
                    'null_fields': null_field_list,
                    'collected_at': str(crawl_dt) if crawl_dt else None
                })

            # 총 개수 조회
            cursor.execute(f"""
                SELECT COUNT(*)
                FROM {db_table}
                WHERE DATE({date_field}::timestamp) = %s
                  AND account_name = %s
                  AND ({null_conditions})
            """, (target_date, retailer))
            results['total'] = cursor.fetchone()[0]

        elif validation_type == 'format':
            # 형식 검증 상세 - TV와 HHP에 맞는 형식 오류 조회
            if table_name == 'TV Retail':
                format_errors = get_tv_format_errors(cursor, db_table, date_field, target_date, retailer)
            else:
                format_errors = get_hhp_format_errors(cursor, db_table, date_field, target_date, retailer)

            results['records'] = format_errors[:100]
            results['total'] = len(format_errors)

        elif validation_type == 'anomaly':
            # 이상치 검증 상세 - 중복 레코드 조회
            cursor.execute(f"""
                SELECT item, COUNT(*) as cnt
                FROM {db_table}
                WHERE DATE({date_field}::timestamp) = %s
                  AND account_name = %s
                GROUP BY item
                HAVING COUNT(*) > 1
                ORDER BY cnt DESC
                LIMIT 100
            """, (target_date, retailer))

            rows = cursor.fetchall()
            for row in rows:
                results['records'].append({
                    'id': '-',
                    'item': row[0],
                    'duplicate_type': f'중복 {row[1]}건',
                    'collected_at': str(target_date)
                })

            results['total'] = len(rows)

        cursor.close()
        conn.close()

    except Exception as e:
        results['error'] = log_error(e)

    return JsonResponse(results)


def get_tv_format_errors(cursor, table_name, date_field, target_date, retailer):
    """TV 형식 오류 데이터 조회 - validate_tv_field 기반 (대시보드 카운트와 동일 로직)"""
    errors = []

    all_fields = [
        'item', 'page_type', 'product_url', 'main_rank', 'bsr_rank',
        'final_sku_price', 'original_sku_price',
        'count_of_reviews', 'star_rating', 'count_of_star_ratings',
        'detailed_review_content',
        'number_of_units_purchased_past_month', 'available_quantity_for_purchase',
        'sku_popularity', 'retailer_membership_discounts',
        'rank_1', 'rank_2', 'summarized_review_content',
        'savings', 'offer', 'retailer_sku_name_similar', 'recommendation_intent',
        'number_of_ppl_purchased_yesterday', 'number_of_ppl_added_to_carts', 'discount_type'
    ]

    cursor.execute(f"""
        SELECT
            id, item, {date_field}, product_url,
            item, page_type, product_url, main_rank, bsr_rank,
            final_sku_price, original_sku_price,
            count_of_reviews, star_rating, count_of_star_ratings,
            detailed_review_content,
            number_of_units_purchased_past_month, available_quantity_for_purchase,
            sku_popularity, retailer_membership_discounts,
            rank_1, rank_2, summarized_review_content,
            savings, offer, retailer_sku_name_similar, recommendation_intent,
            number_of_ppl_purchased_yesterday, number_of_ppl_added_to_carts, discount_type
        FROM {table_name}
        WHERE DATE({date_field}::timestamp) = %s
          AND account_name = %s
        ORDER BY id
    """, (target_date, retailer))

    for row in cursor.fetchall():
        record_id = row[0]
        item = row[1]
        crawl_dt = row[2]
        product_url = row[3]
        values = list(row[4:])

        row_errors = []
        for field, value in zip(all_fields, values):
            error = validate_tv_field(field, value, retailer)
            if error:
                row_errors.append(field)

        if row_errors:
            errors.append({
                'id': record_id,
                'item': item,
                'error_field': ', '.join(row_errors),
                'error_value': ', '.join(row_errors),
                'collected_at': str(crawl_dt) if crawl_dt else None
            })

    return errors


def get_hhp_format_errors(cursor, table_name, date_field, target_date, retailer):
    """HHP 형식 오류 데이터 조회 - validate_hhp_field 기반 (대시보드 카운트와 동일 로직)"""
    errors = []

    hhp_fields = [
        'item', 'page_type', 'product_url', 'main_rank', 'bsr_rank', 'trend_rank',
        'final_sku_price', 'original_sku_price',
        'count_of_reviews', 'star_rating', 'count_of_star_ratings',
        'detailed_review_content', 'trade_in', 'sku_status',
        'number_of_units_purchased_past_month', 'available_quantity_for_purchase',
        'sku_popularity', 'retailer_membership_discounts',
        'rank_1', 'rank_2', 'summarized_review_content',
        'savings', 'offer', 'retailer_sku_name_similar', 'recommendation_intent',
        'number_of_ppl_purchased_yesterday', 'number_of_ppl_added_to_carts', 'discount_type'
    ]

    cursor.execute(f"""
        SELECT
            id, item, {date_field}, product_url,
            item, page_type, product_url, main_rank, bsr_rank, trend_rank,
            final_sku_price, original_sku_price,
            count_of_reviews, star_rating, count_of_star_ratings,
            detailed_review_content, trade_in, sku_status,
            number_of_units_purchased_past_month, available_quantity_for_purchase,
            sku_popularity, retailer_membership_discounts,
            rank_1, rank_2, summarized_review_content,
            savings, offer, retailer_sku_name_similar, recommendation_intent,
            number_of_ppl_purchased_yesterday, number_of_ppl_added_to_carts, discount_type
        FROM {table_name}
        WHERE DATE({date_field}::timestamp) = %s
          AND account_name = %s
        ORDER BY id
    """, (target_date, retailer))

    for row in cursor.fetchall():
        record_id = row[0]
        item = row[1]
        crawl_dt = row[2]
        product_url = row[3]
        values = list(row[4:])

        row_errors = []
        for field, value in zip(hhp_fields, values):
            error = validate_hhp_field(field, value, retailer)
            if error:
                row_errors.append(field)

        if row_errors:
            errors.append({
                'id': record_id,
                'item': item,
                'error_field': ', '.join(row_errors),
                'error_value': ', '.join(row_errors),
                'collected_at': str(crawl_dt) if crawl_dt else None
            })

    return errors


def format_rules(request):
    """형식검증 규칙 조회 API - DB 기반 (신규 테이블)"""
    table_name = request.GET.get('table', 'tv_retail_com')
    if table_name not in VALID_TABLES_RULES:
        return JsonResponse({'error': '잘못된 테이블 파라미터'}, status=400)
    retailer = request.GET.get('retailer', 'Amazon')

    try:
        conn = get_dx_connection()
        cursor = conn.cursor()
        tbl_rules = dx_table('monitoring_format_rules')
        tbl_templates = dx_table('monitoring_format_templates')

        cursor.execute(f"""
            SELECT r.column_name, t.check_type, t.pattern,
                   r.rule_value, r.extra_allowed,
                   r.error_message
            FROM {tbl_rules} r
            LEFT JOIN {tbl_templates} t ON r.template_id = t.id
            WHERE r.table_name = %s AND r.account_name = %s
              AND r.is_active = TRUE AND r.is_del = FALSE
              AND (t.id IS NULL OR t.is_active = TRUE)
            ORDER BY r.column_name
        """, (table_name, retailer))

        cols = [desc[0] for desc in cursor.description]
        rows = [dict(zip(cols, row)) for row in cursor.fetchall()]
        cursor.close()
        conn.close()
    except Exception as e:
        log_error(e, 'db')
        return JsonResponse({'rules': []})

    result = []
    for row in rows:
        check_type = row.get('check_type') or ''
        pattern = row.get('pattern') or ''
        rule_value = row.get('rule_value') or ''
        extra_allowed = row.get('extra_allowed') or ''
        error_message = row.get('error_message') or ''

        patterns = []
        description = ''

        # 메인 검증 규칙 (template 기반)
        if check_type:
            if check_type in ('regex', 'regex_clean'):
                patterns.append(pattern)
                description = error_message or _get_description_for_type(check_type, pattern, [])
            elif check_type == 'range':
                parts = rule_value.split('~')
                if len(parts) == 2:
                    patterns.append(f'{parts[0]} ~ {parts[1]}')
                    description = error_message or f'{parts[0]}~{parts[1]} 범위 정수'
            elif check_type == 'range_float':
                parts = rule_value.split('~')
                if len(parts) == 2:
                    patterns.append(f'{parts[0]} ~ {parts[1]}')
                    description = error_message or f'{parts[0]}~{parts[1]} 범위'
            elif check_type == 'enum':
                allowed_list = [v.strip() for v in rule_value.split('|') if v.strip()] if rule_value else []
                patterns.append(' | '.join(allowed_list))
                description = error_message or '허용값만'
            elif check_type == 'starts_with':
                patterns.append(f'"{rule_value}..."')
                description = error_message or f'{rule_value}로 시작'
            elif check_type == 'separator_count':
                parts = rule_value.split('~')
                if len(parts) == 2:
                    patterns.append(f'{parts[0]} 구분자 {parts[1]}개')
                    description = error_message or f'{parts[0]} 구분자 {parts[1]}개 필요'
            elif check_type == 'fk_check':
                patterns.append(f'참조: {rule_value}')
                description = error_message or 'FK 참조 검증'
            elif check_type == 'min':
                patterns.append(f'>= {rule_value}')
                description = error_message or f'{rule_value} 이상'

        # extra_allowed 표시
        if extra_allowed:
            allowed_list = [v.strip() for v in extra_allowed.split('|') if v.strip()]
            for val in allowed_list:
                patterns.append(f'"{val}"')

        if patterns:
            result.append({
                'field': row['column_name'],
                'description': description or '형식 검증',
                'pattern': '\n'.join(patterns)
            })

    # 필드명 알파벳순 정렬
    result.sort(key=lambda x: x['field'])

    return JsonResponse({'rules': result})


def _get_description_for_type(rule_type, rule_value, allowed):
    """규칙 타입별 설명 생성"""
    if rule_type == 'regex':
        if rule_value == '^[A-Za-z0-9]+$':
            return '알파벳+숫자만 허용'
        elif '\\$' in rule_value:
            return '$금액 형식'
        elif '\\d' in rule_value:
            return '숫자 형식'
        elif 'http' in rule_value:
            return 'http:// 또는 https:// 시작'
        else:
            return '정규식 패턴'
    return '형식 검증'


# ============================================================
# 셀 수정 API
# ============================================================

VALID_TABLES_UPDATE = {
    'tv_retail_com', 'hhp_retail_com',
    'youtube_collection_logs', 'youtube_videos', 'youtube_comments',
    'market_trend', 'market_comp_product', 'market_comp_event', 'openai_forecast_results',
}


def update_cell(request):
    """셀 값 수정 API (POST)"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST only'}, status=405)

    import json
    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': '잘못된 요청 형식'}, status=400)

    table_name = body.get('table_name', '')
    row_id = body.get('row_id')
    column_name = body.get('column_name', '')
    new_value = body.get('new_value')
    crawl_date = body.get('crawl_date')
    correction_type = body.get('correction_type', 'null')
    # correction_type 화이트리스트 검증
    valid_correction_types = {'null': 'null_check', 'format': 'format_check', 'duplicate': 'duplicate_check'}
    correction_type_value = valid_correction_types.get(correction_type, 'null_check')

    # 필수 파라미터 검증
    if not all([table_name, row_id, column_name]):
        return JsonResponse({'error': '필수 파라미터 누락'}, status=400)

    # 테이블 화이트리스트 검증
    if table_name not in VALID_TABLES_UPDATE:
        return JsonResponse({'error': '수정 불가능한 테이블'}, status=400)

    # 컬럼명 안전성 검증 (영문, 숫자, 언더스코어만)
    import re
    if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', column_name):
        return JsonResponse({'error': '잘못된 컬럼명'}, status=400)

    # is_editable 검증
    product_line = 'tv' if table_name == 'tv_retail_com' else 'hhp'
    # retailer는 row에서 조회
    conn = None
    try:
        conn = get_dx_connection()
        cursor = conn.cursor()

        # 기존 값 + retailer + item 조회
        cursor.execute(
            f"SELECT {column_name}, account_name, item FROM {table_name} WHERE id = %s",
            (row_id,)
        )
        row = cursor.fetchone()
        if not row:
            cursor.close()
            conn.close()
            return JsonResponse({'error': '해당 레코드가 없습니다'}, status=404)

        old_value = row[0]
        retailer = row[1]
        item_value = str(row[2]) if row[2] else ''

        # editable 컬럼 확인
        editable_cols = get_editable_columns(product_line, retailer)
        if column_name not in editable_cols:
            cursor.close()
            conn.close()
            return JsonResponse({'error': f'{column_name} 컬럼은 수정할 수 없습니다'}, status=403)

        # 값이 같으면 스킵
        old_str = str(old_value) if old_value is not None else ''
        new_str = str(new_value) if new_value is not None else ''
        if old_str == new_str:
            cursor.close()
            conn.close()
            return JsonResponse({'success': True, 'message': '변경 없음'})

        # UPDATE 실행
        update_value = new_value if new_value != '' else None
        cursor.execute(
            f"UPDATE {table_name} SET {column_name} = %s WHERE id = %s",
            (update_value, row_id)
        )

        # monitoring_corrections에 이력 저장
        now = datetime.now()
        user_id = request.user.username if request.user.is_authenticated else 'anonymous'
        memo = body.get('memo', '') or None
        cursor.execute("""
            INSERT INTO monitoring_corrections
                (layer, correction_type, table_name, record_id, column_name,
                 old_value, new_value, crawl_date, created_id, created_at, status, memo, retailer, item)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            2, correction_type_value, table_name, row_id, column_name,
            str(old_value) if old_value is not None else None,
            str(new_value) if new_value is not None else None,
            crawl_date, user_id, now, 'corrected', memo, retailer, item_value or None
        ))

        conn.commit()
        cursor.close()
        conn.close()

        return JsonResponse({'success': True, 'old_value': old_str, 'new_value': new_str})

    except Exception as e:
        if conn:
            try:
                conn.rollback()
                conn.close()
            except Exception:
                pass
        return safe_error(e)


def review_reasons(request):
    """정상 처리 이유 목록 조회 API (GET) — 코드 상수에서 반환"""
    from apps.common.constants import get_reasons
    check_type = request.GET.get('check_type', 'null_check')
    reasons = [{'text': r} for r in get_reasons(check_type)]
    return JsonResponse({'success': True, 'reasons': reasons})


def null_review(request):
    """NULL 검증 정상 처리 / 취소 API (POST)"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST only'}, status=405)

    import json
    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': '잘못된 요청 형식'}, status=400)

    table_name = body.get('table_name', '')
    record_id = body.get('record_id')
    column_name = body.get('column_name', '')
    status = body.get('status', '')  # 'normal' or 'reverted'
    memo = body.get('memo', '')
    reason = body.get('reason', '')  # 사유 텍스트
    crawl_date = body.get('crawl_date')
    correction_type = body.get('correction_type', 'null')
    valid_correction_types = {'null': 'null_check', 'format': 'format_check', 'duplicate': 'duplicate_check'}
    correction_type_value = valid_correction_types.get(correction_type, 'null_check')

    if not all([table_name, record_id, column_name, status]):
        return JsonResponse({'error': '필수 파라미터 누락'}, status=400)

    # 정상 처리만 허용 (reverted 불가)
    if status != 'normal':
        return JsonResponse({'error': '잘못된 status 값'}, status=400)

    if not reason:
        return JsonResponse({'error': '이유 선택은 필수입니다'}, status=400)

    if table_name not in VALID_TABLES_UPDATE:
        return JsonResponse({'error': '허용되지 않는 테이블'}, status=400)

    import re
    if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', column_name):
        return JsonResponse({'error': '잘못된 컬럼명'}, status=400)

    conn = None
    try:
        conn = get_dx_connection()
        cursor = conn.cursor()

        # 현재 값 + account_name + item 조회
        cursor.execute(
            f"SELECT {column_name}, account_name, item FROM {table_name} WHERE id = %s",
            (record_id,)
        )
        row = cursor.fetchone()
        if not row:
            cursor.close()
            conn.close()
            return JsonResponse({'error': '해당 레코드가 없습니다'}, status=404)

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
            cursor.close()
            conn.close()
            return JsonResponse({'error': '이미 정상처리된 항목입니다'}, status=400)

        now = datetime.now()
        user_id = request.user.username if request.user.is_authenticated else 'anonymous'

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
            crawl_date, user_id, now, status, memo or None,
            reason or None, retailer or None, item_value
        ))

        conn.commit()
        cursor.close()
        conn.close()

        return JsonResponse({'success': True, 'status': status})

    except Exception as e:
        if conn:
            try:
                conn.rollback()
                conn.close()
            except Exception:
                pass
        return safe_error(e)
