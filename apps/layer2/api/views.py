"""
Layer 2 API: 형식/NULL 검증 (Formatting & Null Validation)
- 검증유형별 분류: NULL검증, 형식검증, 이상치검증
- 테이블별 분류: TV Retail, HHP Retail, Sentiment, YouTube, Market
"""

from django.http import JsonResponse
from datetime import datetime, timedelta
from apps.common.db import get_dx_connection
from apps.common.retail_columns import (
    get_null_check_query_parts, get_null_detail_query_parts, get_null_check_columns,
    validate_field, get_duplicate_key_columns, get_duplicate_check_query,
    load_format_rules, get_retailer_list, get_retail_duplicate_keys,
    get_null_check_config, get_null_display_columns, get_null_query_columns,
    get_null_check_where_condition, get_null_check_date_column,
    get_check_name_by_table, get_check_names_by_table, get_null_check_columns_for_category,
    get_all_categories, get_check_names_by_category, get_category_config
)


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
    return validate_field('tv_retail_com', field_name, value, account_name)


def validate_hhp_field(field_name, value, account_name='Amazon'):
    """HHP Retail 필드별 형식 검증. 오류 시 메시지 반환, 정상이면 None (CSV 기반)"""
    return validate_field('hhp_retail_com', field_name, value, account_name)


def layer_stats(request):
    """Layer 2 통계 API - 검증유형별, 테이블별 구조화"""
    date_str = request.GET.get('date')

    if date_str:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    else:
        target_date = (datetime.now() - timedelta(days=1)).date()

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

                            cat_retailers.append({
                                'retailer': retailer_name,
                                'total': total,
                                'records_with_null': total_null_count,  # 필드별 NULL 합산
                                'status': get_status(total_null_count),
                                'fields_detail': fields_detail
                            })
                            cat_total_records += total
                            cat_total_issues += total_null_count
                    except Exception:
                        # 개별 check_name 오류 시 무시하고 계속
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
            except Exception:
                # category 처리 오류 시 무시하고 계속
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

        # TV Retail 형식 검증 - 리테일러별 전체 필드 검증
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
            LIMIT 10000
        """, (target_date,))

        tv_format_rows = cursor.fetchall()
        tv_format_errors = []
        tv_format_by_retailer = {'Amazon': 0, 'Bestbuy': 0, 'Walmart': 0}
        tv_format_total_by_retailer = {'Amazon': 0, 'Bestbuy': 0, 'Walmart': 0}

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

        for row in tv_format_rows:
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
                    'error': f'tv_item_mst에 등록되지 않은 item: {item_value}'
                })

            if errors:
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
            'total_checked': len(tv_format_rows),
            'total_issues': tv_format_issue_total,
            'status': get_status(tv_format_issue_total),
            'retailers': tv_format_retailers,
            'sample_errors': tv_format_errors[:30]
        })
        total_format_issues += tv_format_issue_total

        # hhp_item_mst에서 유효한 item 목록 조회 (HHP Retail 참조 무결성 검증용)
        cursor.execute("SELECT DISTINCT item FROM hhp_item_mst")
        hhp_valid_items = set(row[0] for row in cursor.fetchall())

        # HHP Retail 형식 검증 - 리테일러별 전체 필드 검증 (HHP 전용 필드 포함)
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
            LIMIT 10000
        """, (target_date,))

        hhp_format_rows = cursor.fetchall()
        hhp_format_errors = []
        hhp_format_by_retailer = {'Amazon': 0, 'Bestbuy': 0, 'Walmart': 0}
        hhp_format_total_by_retailer = {'Amazon': 0, 'Bestbuy': 0, 'Walmart': 0}

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

        for row in hhp_format_rows:
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
                    'error': f'hhp_item_mst에 등록되지 않은 item: {item_value}'
                })

            if errors:
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
            'total_checked': len(hhp_format_rows),
            'total_issues': hhp_format_issue_total,
            'status': get_status(hhp_format_issue_total),
            'retailers': hhp_format_retailers,
            'sample_errors': hhp_format_errors[:30]
        })
        total_format_issues += hhp_format_issue_total

        # YouTube 형식 검증 (Logs, Videos, Comments 통합)
        # Logs 형식 검증
        cursor.execute("""
            SELECT
                COUNT(*) as total,
                COUNT(CASE WHEN l.keyword IS NOT NULL AND l.keyword NOT IN (SELECT keyword FROM youtube_keywords WHERE status = 'active') THEN 1 END) as invalid_keyword,
                COUNT(CASE WHEN l.status IS NOT NULL AND l.status NOT IN ('failed', 'completed') THEN 1 END) as invalid_status,
                COUNT(CASE WHEN videos_collected IS NOT NULL AND videos_collected < 0 THEN 1 END) as invalid_videos_collected,
                COUNT(CASE WHEN comments_collected IS NOT NULL AND comments_collected < 0 THEN 1 END) as invalid_comments_collected
            FROM youtube_collection_logs l
            WHERE DATE(l.started_at) = %s
        """, (target_date,))
        yt_log_format_row = cursor.fetchone()
        # None 값을 0으로 변환하여 합산
        yt_log_format_issues = sum(v or 0 for v in yt_log_format_row[1:5]) if yt_log_format_row else 0

        # Videos 형식 검증
        cursor.execute("""
            SELECT
                COUNT(*) as total,
                COUNT(CASE WHEN v.keyword IS NOT NULL AND v.keyword NOT IN (SELECT keyword FROM youtube_keywords WHERE status = 'active') THEN 1 END) as invalid_keyword,
                COUNT(CASE WHEN published_at IS NOT NULL AND created_at IS NOT NULL AND published_at > created_at THEN 1 END) as invalid_published_at,
                COUNT(CASE WHEN channel_custom_url IS NOT NULL AND channel_custom_url != '' AND LEFT(channel_custom_url, 1) != '@' THEN 1 END) as invalid_channel_url,
                COUNT(CASE WHEN channel_subscriber_count IS NOT NULL AND channel_subscriber_count < 0 THEN 1 END) as invalid_subscriber_count,
                COUNT(CASE WHEN channel_video_count IS NOT NULL AND channel_video_count < 0 THEN 1 END) as invalid_video_count,
                COUNT(CASE WHEN view_count IS NOT NULL AND view_count < 0 THEN 1 END) as invalid_view_count,
                COUNT(CASE WHEN like_count IS NOT NULL AND like_count < 0 THEN 1 END) as invalid_like_count,
                COUNT(CASE WHEN comment_count IS NOT NULL AND comment_count < 0 THEN 1 END) as invalid_comment_count,
                COUNT(CASE WHEN category IS NOT NULL AND category NOT IN ('TV', 'HHP') THEN 1 END) as invalid_category,
                COUNT(CASE WHEN engagement_rate IS NOT NULL AND engagement_rate < 2.0 THEN 1 END) as invalid_engagement_rate,
                COUNT(CASE WHEN product_sentiment_score IS NOT NULL AND (product_sentiment_score < -5.0 OR product_sentiment_score > 5.0) THEN 1 END) as invalid_sentiment_score
            FROM youtube_videos v
            WHERE DATE(created_at) = %s
        """, (target_date,))
        yt_video_format_row = cursor.fetchone()
        # None 값을 0으로 변환하여 합산
        yt_video_format_issues = sum(v or 0 for v in yt_video_format_row[1:12]) if yt_video_format_row else 0

        # Comments 형식 검증
        cursor.execute("""
            SELECT
                COUNT(*) as total,
                COUNT(CASE WHEN c.video_id IS NOT NULL AND c.video_id NOT IN (SELECT video_id FROM youtube_videos) THEN 1 END) as invalid_video_id,
                COUNT(CASE WHEN comment_type IS NOT NULL AND comment_type NOT IN ('top_level', 'reply') THEN 1 END) as invalid_comment_type,
                COUNT(CASE WHEN parent_comment_id IS NOT NULL AND parent_comment_id != '' AND comment_type = 'top_level' THEN 1 END) as invalid_parent_comment,
                COUNT(CASE WHEN like_count IS NOT NULL AND like_count < 0 THEN 1 END) as invalid_like_count,
                COUNT(CASE WHEN reply_count IS NOT NULL AND reply_count < 0 THEN 1 END) as invalid_reply_count,
                COUNT(CASE WHEN published_at IS NOT NULL AND created_at IS NOT NULL AND published_at > created_at THEN 1 END) as invalid_published_at
            FROM youtube_comments c
            WHERE DATE(created_at) = %s
        """, (target_date,))
        yt_comment_format_row = cursor.fetchone()
        # None 값을 0으로 변환하여 합산
        yt_comment_format_issues = sum(v or 0 for v in yt_comment_format_row[1:7]) if yt_comment_format_row else 0

        # YouTube 통합 (리테일러 형태로) - 순서: Logs, Videos, Comments
        yt_total_format_issues = yt_log_format_issues + yt_video_format_issues + yt_comment_format_issues

        # 안전한 인덱스 접근 헬퍼 함수
        def safe_get(row, idx, default=0):
            if row is None or idx >= len(row):
                return default
            return row[idx] if row[idx] is not None else default

        yt_total_format_checked = safe_get(yt_log_format_row, 0) + safe_get(yt_video_format_row, 0) + safe_get(yt_comment_format_row, 0)

        youtube_format_retailers = [
            {
                'retailer': 'Logs',
                'total': safe_get(yt_log_format_row, 0),
                'issue_count': yt_log_format_issues,
                'status': get_status(yt_log_format_issues),
                'fields_detail': {
                    'keyword 비활성': safe_get(yt_log_format_row, 1),
                    'status 값 오류': safe_get(yt_log_format_row, 2),
                    'videos_collected 음수': safe_get(yt_log_format_row, 3),
                    'comments_collected 음수': safe_get(yt_log_format_row, 4)
                }
            },
            {
                'retailer': 'Videos',
                'total': safe_get(yt_video_format_row, 0),
                'issue_count': yt_video_format_issues,
                'status': get_status(yt_video_format_issues),
                'fields_detail': {
                    'keyword 비활성': safe_get(yt_video_format_row, 1),
                    'published_at > created_at': safe_get(yt_video_format_row, 2),
                    'channel_url @누락': safe_get(yt_video_format_row, 3),
                    'subscriber_count 음수': safe_get(yt_video_format_row, 4),
                    'video_count 음수': safe_get(yt_video_format_row, 5),
                    'view_count 음수': safe_get(yt_video_format_row, 6),
                    'like_count 음수': safe_get(yt_video_format_row, 7),
                    'comment_count 음수': safe_get(yt_video_format_row, 8),
                    'category 오류': safe_get(yt_video_format_row, 9),
                    'engagement_rate < 2.0': safe_get(yt_video_format_row, 10),
                    'sentiment 범위 오류': safe_get(yt_video_format_row, 11)
                }
            },
            {
                'retailer': 'Comments',
                'total': safe_get(yt_comment_format_row, 0),
                'issue_count': yt_comment_format_issues,
                'status': get_status(yt_comment_format_issues),
                'fields_detail': {
                    'video_id 참조 오류': safe_get(yt_comment_format_row, 1),
                    'comment_type 오류': safe_get(yt_comment_format_row, 2),
                    'parent_comment 오류': safe_get(yt_comment_format_row, 3),
                    'like_count 음수': safe_get(yt_comment_format_row, 4),
                    'reply_count 음수': safe_get(yt_comment_format_row, 5),
                    'published_at > created_at': safe_get(yt_comment_format_row, 6)
                }
            }
        ]

        format_validation['tables'].append({
            'table': 'youtube',
            'table_name': 'YouTube',
            'total_checked': yt_total_format_checked,
            'total_issues': yt_total_format_issues,
            'status': get_status(yt_total_format_issues),
            'retailers': youtube_format_retailers
        })
        total_format_issues += yt_total_format_issues

        # Market 형식 검증 (Trend, Comp Product, Comp Event)
        try:
            # market_trend 형식 검증
            cursor.execute("""
                SELECT
                    COUNT(*) as total,
                    COUNT(CASE WHEN keyword IS NOT NULL AND keyword != '' AND keyword NOT IN (SELECT keyword FROM market_mst WHERE analysis_type = 'trend') THEN 1 END) as invalid_keyword,
                    COUNT(CASE WHEN total_article_number IS NOT NULL AND total_article_number < 0 THEN 1 END) as invalid_total_article_number,
                    COUNT(CASE WHEN calendar_week IS NOT NULL AND calendar_week != '' AND calendar_week !~ '^W(0[1-9]|[1-4][0-9]|5[0-2])$' THEN 1 END) as invalid_calendar_week
                FROM market_trend
                WHERE DATE(crawl_at_local_time) = %s
            """, (target_date,))
            market_trend_format_row = cursor.fetchone()
            market_trend_format_issues = sum(v or 0 for v in market_trend_format_row[1:4]) if market_trend_format_row else 0

            # market_comp_product 형식 검증
            cursor.execute("""
                SELECT
                    COUNT(*) as total,
                    COUNT(CASE WHEN samsung_series_name IS NOT NULL AND samsung_series_name != '' AND samsung_series_name NOT IN (SELECT keyword FROM market_mst WHERE analysis_type = 'competitor' AND content_type = 'samsung') THEN 1 END) as invalid_samsung_series,
                    COUNT(CASE WHEN comp_brand IS NOT NULL AND comp_brand != '' AND comp_brand NOT IN (SELECT keyword FROM market_mst WHERE analysis_type = 'competitor' AND content_type = 'comp') THEN 1 END) as invalid_comp_brand,
                    COUNT(CASE WHEN calender_week IS NOT NULL AND calender_week != '' AND LOWER(calender_week) !~ '^w([1-9]|[1-4][0-9]|5[0-2])$' THEN 1 END) as invalid_calender_week,
                    COUNT(CASE WHEN category IS NOT NULL AND category != '' AND category NOT IN ('TV', 'HHP') THEN 1 END) as invalid_category
                FROM market_comp_product
                WHERE DATE(created_at) = %s
            """, (target_date,))
            market_comp_product_format_row = cursor.fetchone()
            market_comp_product_format_issues = sum(v or 0 for v in market_comp_product_format_row[1:5]) if market_comp_product_format_row else 0

            # market_comp_event 형식 검증 - 최신 배치 기준 comp_brand, comp_series_name 검증
            cursor.execute("""
                WITH latest_batch AS (
                    SELECT comp_brand, comp_series_name FROM market_comp_product
                    WHERE batch_id = (SELECT MAX(batch_id) FROM market_comp_product WHERE DATE(created_at) <= %s)
                )
                SELECT
                    COUNT(*) as total,
                    COUNT(CASE WHEN e.comp_brand IS NOT NULL AND e.comp_brand != '' AND e.comp_brand NOT IN (SELECT comp_brand FROM latest_batch) THEN 1 END) as invalid_comp_brand,
                    COUNT(CASE WHEN e.comp_sku_name IS NOT NULL AND e.comp_sku_name != '' AND e.comp_sku_name NOT IN (SELECT comp_series_name FROM latest_batch) THEN 1 END) as invalid_comp_sku_name,
                    COUNT(CASE WHEN e.calender_week IS NOT NULL AND e.calender_week != '' AND LOWER(e.calender_week) !~ '^w([1-9]|[1-4][0-9]|5[0-2])$' THEN 1 END) as invalid_calender_week,
                    COUNT(CASE WHEN e.category IS NOT NULL AND e.category != '' AND e.category NOT IN ('TV', 'HHP') THEN 1 END) as invalid_category
                FROM market_comp_event e
                WHERE DATE(e.created_at) = %s
            """, (target_date, target_date))
            market_comp_event_format_row = cursor.fetchone()
            market_comp_event_format_issues = sum(v or 0 for v in market_comp_event_format_row[1:5]) if market_comp_event_format_row else 0

            # openai_forecast_results 형식 검증
            cursor.execute("""
                SELECT
                    COUNT(*) as total,
                    COUNT(CASE WHEN product_name IS NOT NULL AND product_name != '' AND product_name NOT IN (SELECT product_name FROM openai_keywords WHERE is_active = true) THEN 1 END) as invalid_product_name,
                    COUNT(CASE WHEN event IS NOT NULL AND event != '' AND REPLACE(LOWER(event), ' ', '_') NOT IN (SELECT LOWER(REPLACE(event_name, ' ', '_')) FROM openai_event_mst WHERE is_active = true) THEN 1 END) as invalid_event,
                    COUNT(CASE WHEN metric_type IS NOT NULL AND metric_type != '' AND metric_type != 'Forecasted_NA_sales_change' THEN 1 END) as invalid_metric_type,
                    COUNT(CASE WHEN event_offset IS NOT NULL AND (event_offset < 0 OR event_offset > 9) THEN 1 END) as invalid_event_offset,
                    COUNT(CASE WHEN event_value IS NOT NULL AND event_value::text !~ '^-?[0-9]+\.?[0-9]*$' THEN 1 END) as invalid_event_value_format,
                    COUNT(CASE WHEN event_value IS NOT NULL AND (event_value < -50 OR event_value > 100) THEN 1 END) as invalid_event_value_range,
                    COUNT(CASE WHEN week IS NOT NULL AND week != '' AND week !~ '^w[0-9]{1,2}$' THEN 1 END) as invalid_week,
                    COUNT(CASE WHEN crawled_at IS NOT NULL AND crawled_at::text !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$' THEN 1 END) as invalid_crawled_at
                FROM openai_forecast_results
                WHERE DATE(crawled_at) = %s
            """, (target_date,))
            forecast_format_row = cursor.fetchone()
            forecast_format_issues = sum(v or 0 for v in forecast_format_row[1:9]) if forecast_format_row else 0

            market_total_format_checked = (market_trend_format_row[0] if market_trend_format_row else 0) + \
                                           (market_comp_product_format_row[0] if market_comp_product_format_row else 0) + \
                                           (market_comp_event_format_row[0] if market_comp_event_format_row else 0) + \
                                           (forecast_format_row[0] if forecast_format_row else 0)
            market_total_format_issues = market_trend_format_issues + market_comp_product_format_issues + market_comp_event_format_issues + forecast_format_issues

            market_format_retailers = [
                {
                    'retailer': 'Trend',
                    'total': market_trend_format_row[0] if market_trend_format_row else 0,
                    'issue_count': market_trend_format_issues,
                    'status': get_status(market_trend_format_issues),
                    'fields_detail': {
                        'keyword 미등록': market_trend_format_row[1] if market_trend_format_row else 0,
                        'total_article_number 음수': market_trend_format_row[2] if market_trend_format_row else 0,
                        'calendar_week 형식 오류': market_trend_format_row[3] if market_trend_format_row else 0
                    }
                },
                {
                    'retailer': 'Comp Product',
                    'total': market_comp_product_format_row[0] if market_comp_product_format_row else 0,
                    'issue_count': market_comp_product_format_issues,
                    'status': get_status(market_comp_product_format_issues),
                    'fields_detail': {
                        'samsung_series_name 미등록': market_comp_product_format_row[1] if market_comp_product_format_row else 0,
                        'comp_brand 미등록': market_comp_product_format_row[2] if market_comp_product_format_row else 0,
                        'calender_week 형식 오류': market_comp_product_format_row[3] if market_comp_product_format_row else 0,
                        'category 값 오류': market_comp_product_format_row[4] if market_comp_product_format_row else 0
                    }
                },
                {
                    'retailer': 'Comp Event',
                    'total': market_comp_event_format_row[0] if market_comp_event_format_row else 0,
                    'issue_count': market_comp_event_format_issues,
                    'status': get_status(market_comp_event_format_issues),
                    'fields_detail': {
                        'comp_brand 미등록': market_comp_event_format_row[1] if market_comp_event_format_row else 0,
                        'comp_sku_name 미등록': market_comp_event_format_row[2] if market_comp_event_format_row else 0,
                        'calender_week 형식 오류': market_comp_event_format_row[3] if market_comp_event_format_row else 0,
                        'category 값 오류': market_comp_event_format_row[4] if market_comp_event_format_row else 0
                    }
                },
                {
                    'retailer': 'Forecast',
                    'total': forecast_format_row[0] if forecast_format_row else 0,
                    'issue_count': forecast_format_issues,
                    'status': get_status(forecast_format_issues),
                    'fields_detail': {
                        'product_name 미등록': forecast_format_row[1] if forecast_format_row else 0,
                        'event 미등록': forecast_format_row[2] if forecast_format_row else 0,
                        'metric_type 값 오류': forecast_format_row[3] if forecast_format_row else 0,
                        'event_offset 범위 오류 (0~9)': forecast_format_row[4] if forecast_format_row else 0,
                        'event_value 형식 오류': forecast_format_row[5] if forecast_format_row else 0,
                        'event_value 범위 오류 (-50~100%)': forecast_format_row[6] if forecast_format_row else 0,
                        'week 형식 오류': forecast_format_row[7] if forecast_format_row else 0,
                        'crawled_at 형식 오류': forecast_format_row[8] if forecast_format_row else 0
                    }
                }
            ]

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
            pass  # Market 테이블이 없거나 컬럼이 다른 경우 무시

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
        tv_dup_retailers = []
        tv_dup_total = 0
        for retailer_name in retailer_list:
            dup_count = tv_dup_dict.get(retailer_name, 0)
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
        hhp_dup_retailers = []
        hhp_dup_total = 0
        for retailer_name in retailer_list:
            dup_count = hhp_dup_dict.get(retailer_name, 0)
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

        cursor.close()
        conn.close()

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
        import traceback
        results['error'] = str(e)
        results['error_detail'] = traceback.format_exc()
        results['summary']['overall_status'] = 'ERROR'
        print(f"[Layer2 DX Error] {e}")
        print(traceback.format_exc())

    return JsonResponse(results)


def null_detail(request):
    """NULL 필드 상세 조회 API - category 기반 동적 처리"""
    date_str = request.GET.get('date')
    category = request.GET.get('table', 'tv_retail')  # table 파라미터가 category
    retailer = request.GET.get('retailer')

    if date_str:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    else:
        target_date = (datetime.now() - timedelta(days=1)).date()

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
        print(f"[DEBUG] check_name={check_name}, actual_table={actual_table}, date_col={date_col}")
        print(f"[DEBUG] all_null_check_cols={all_null_check_cols}")
        print(f"[DEBUG] category_config columns={category_config['columns']}")

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

        print(f"[DEBUG] query={query}")
        print(f"[DEBUG] params={params}")
        cursor.execute(query, params)
        rows = cursor.fetchall()
        print(f"[DEBUG] rows count={len(rows)}")

        # 컬럼 인덱스 매핑
        col_index = {col: idx for idx, col in enumerate(select_cols)}

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

            # null_fields 계산
            null_fields = []
            for col_name in all_null_check_cols:
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

        print(f"[DEBUG] results count={len(results)}")
        if results:
            print(f"[DEBUG] first result={results[0]}")

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

        cursor.close()
        conn.close()
        return JsonResponse({
            'results': results,
            'display_config': display_config,
            'query_config': query_config,
            'date_column': date_col,
            'date': str(target_date)
        })

    except Exception as e:
        return JsonResponse({'error': str(e)})


def format_detail(request):
    """형식 오류 상세 조회 API"""
    date_str = request.GET.get('date')
    table = request.GET.get('table', 'tv_retail')
    retailer = request.GET.get('retailer')

    if date_str:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    else:
        target_date = (datetime.now() - timedelta(days=1)).date()

    try:
        conn = get_dx_connection()
        cursor = conn.cursor()

        results = []
        next_date = target_date + timedelta(days=1)

        # TV Retail 형식 오류 상세 조회 - validate_tv_field 함수 사용 (layer_stats와 동일)
        if table == 'tv_retail':
            # layer_stats와 동일한 쿼리로 모든 필드 조회
            query = """
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
            """
            params = [str(target_date), str(next_date)]

            if retailer:
                query += " AND account_name = %s"
                params.append(retailer)

            query += " ORDER BY account_name, crawl_datetime LIMIT 500"
            cursor.execute(query, params)
            rows = cursor.fetchall()

            # 전체 필드 목록 (layer_stats와 동일)
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
                errors = []
                record_id = row[0]
                crawl_dt = row[1]
                account_name = row[2]
                item = row[3]
                product_url = row[5]

                # row[3]부터 시작 (row[0]=id, row[1]=crawl_datetime, row[2]=account_name)
                values = list(row[3:])

                for field, value in zip(all_fields, values):
                    error = validate_tv_field(field, value, account_name)
                    if error:
                        errors.append({
                            'field': field,
                            'value': str(value)[:50] if value else '',
                            'rule': error.split(':')[0] if ':' in error else error,
                            'reason': error.split(':')[1].strip() if ':' in error else error
                        })

                if errors:
                    results.append({
                        'id': record_id,
                        'item': item,
                        'crawl_datetime': str(crawl_dt) if crawl_dt else None,
                        'product_url': product_url,
                        'errors': errors
                    })

        # HHP Retail 형식 오류 상세 조회 - validate_hhp_field 함수 사용 (layer_stats와 동일)
        elif table == 'hhp_retail':
            # hhp_item_mst에서 유효한 item 목록 조회 (참조 무결성 검증용)
            cursor.execute("SELECT DISTINCT item FROM hhp_item_mst")
            hhp_valid_items = set(row[0] for row in cursor.fetchall())

            # layer_stats와 동일한 쿼리로 모든 필드 조회
            query = """
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
            """
            params = [str(target_date), str(next_date)]

            if retailer:
                query += " AND account_name = %s"
                params.append(retailer)

            query += " ORDER BY account_name, crawl_strdatetime LIMIT 500"
            cursor.execute(query, params)
            rows = cursor.fetchall()

            # HHP 전용 필드 목록 (layer_stats와 동일 - trend_rank, trade_in, sku_status 포함)
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
                errors = []
                record_id = row[0]
                crawl_dt = row[1]
                account_name = row[2]
                item = row[3]
                product_url = row[5]

                # row[3]부터 시작 (row[0]=id, row[1]=crawl_strdatetime, row[2]=account_name)
                values = list(row[3:])

                for field, value in zip(hhp_fields, values):
                    error = validate_hhp_field(field, value, account_name)
                    if error:
                        errors.append({
                            'field': field,
                            'value': str(value)[:50] if value else '',
                            'rule': error.split(':')[0] if ':' in error else error,
                            'reason': error.split(':')[1].strip() if ':' in error else error
                        })

                # 참조 무결성 검증: item이 hhp_item_mst에 존재하는지 (layer_stats와 동일)
                if item and item not in hhp_valid_items:
                    errors.append({
                        'field': 'item (참조 무결성)',
                        'value': str(item)[:50] if item else '',
                        'rule': '참조 무결성',
                        'reason': f'hhp_item_mst에 등록되지 않은 item'
                    })

                if errors:
                    results.append({
                        'id': record_id,
                        'item': item,
                        'crawl_datetime': str(crawl_dt) if crawl_dt else None,
                        'product_url': product_url,
                        'errors': errors
                    })

        # YouTube 테이블 형식 오류 상세 조회
        elif table == 'youtube_logs' or (table == 'youtube' and retailer == 'Logs'):
            # 먼저 active 키워드 목록 조회
            cursor.execute("SELECT keyword FROM youtube_keywords WHERE status = 'active'")
            active_keywords = set(row[0] for row in cursor.fetchall())

            # 형식 오류가 있는 로그 조회
            cursor.execute("""
                SELECT l.id, l.keyword, l.status, l.videos_collected, l.comments_collected, l.started_at
                FROM youtube_collection_logs l
                WHERE DATE(l.started_at) = %s
                  AND (
                      (l.keyword IS NOT NULL AND l.keyword NOT IN (SELECT keyword FROM youtube_keywords WHERE status = 'active'))
                      OR (l.status IS NOT NULL AND l.status NOT IN ('failed', 'completed'))
                      OR (l.videos_collected IS NOT NULL AND l.videos_collected < 0)
                      OR (l.comments_collected IS NOT NULL AND l.comments_collected < 0)
                  )
                ORDER BY l.started_at DESC
                LIMIT 50
            """, (target_date,))
            rows = cursor.fetchall()
            for row in rows:
                errors = []
                # keyword가 active 키워드 목록에 없으면 오류
                if row[1] and row[1] not in active_keywords:
                    errors.append({
                        'field': 'keyword',
                        'value': str(row[1])[:50],
                        'rule': 'active 키워드만 허용',
                        'reason': '비활성 키워드 사용'
                    })
                if row[2] and row[2] not in ('failed', 'completed'):
                    errors.append({
                        'field': 'status',
                        'value': str(row[2]),
                        'rule': 'failed 또는 completed',
                        'reason': f'허용되지 않은 값: {row[2]}'
                    })
                if row[3] is not None and row[3] < 0:
                    errors.append({
                        'field': 'videos_collected',
                        'value': str(row[3]),
                        'rule': '0 이상',
                        'reason': '음수값'
                    })
                if row[4] is not None and row[4] < 0:
                    errors.append({
                        'field': 'comments_collected',
                        'value': str(row[4]),
                        'rule': '0 이상',
                        'reason': '음수값'
                    })
                # 오류가 있을 때만 결과에 추가
                if errors:
                    results.append({
                        'id': row[0],
                        'keyword': row[1],
                        'status': row[2],
                        'videos_collected': row[3],
                        'comments_collected': row[4],
                        'started_at': str(row[5]) if row[5] else None,
                        'errors': errors
                    })

        elif table == 'youtube_videos' or (table == 'youtube' and retailer == 'Videos'):
            # youtube_videos 테이블은 id 컬럼이 없고 video_id가 PK
            cursor.execute("""
                SELECT v.video_id, v.keyword, v.channel_custom_url, v.category,
                       v.engagement_rate, v.product_sentiment_score, v.published_at, v.created_at,
                       v.channel_subscriber_count, v.channel_video_count, v.view_count, v.like_count, v.comment_count
                FROM youtube_videos v
                WHERE DATE(v.created_at) = %s
                  AND (
                      (v.keyword IS NOT NULL AND v.keyword NOT IN (SELECT keyword FROM youtube_keywords WHERE status = 'active'))
                      OR (v.published_at IS NOT NULL AND v.created_at IS NOT NULL AND v.published_at > v.created_at)
                      OR (v.channel_custom_url IS NOT NULL AND v.channel_custom_url != '' AND LEFT(v.channel_custom_url, 1) != '@')
                      OR (v.category IS NOT NULL AND v.category NOT IN ('TV', 'HHP'))
                      OR (v.engagement_rate IS NOT NULL AND v.engagement_rate < 2.0)
                      OR (v.product_sentiment_score IS NOT NULL AND (v.product_sentiment_score < -5.0 OR v.product_sentiment_score > 5.0))
                      OR (v.channel_subscriber_count IS NOT NULL AND v.channel_subscriber_count < 0)
                      OR (v.channel_video_count IS NOT NULL AND v.channel_video_count < 0)
                      OR (v.view_count IS NOT NULL AND v.view_count < 0)
                      OR (v.like_count IS NOT NULL AND v.like_count < 0)
                      OR (v.comment_count IS NOT NULL AND v.comment_count < 0)
                  )
                ORDER BY v.created_at DESC
                LIMIT 50
            """, (target_date,))
            rows = cursor.fetchall()
            # row[0]=video_id, row[1]=keyword, row[2]=channel_custom_url, row[3]=category,
            # row[4]=engagement_rate, row[5]=product_sentiment_score, row[6]=published_at, row[7]=created_at,
            # row[8]=channel_subscriber_count, row[9]=channel_video_count, row[10]=view_count, row[11]=like_count, row[12]=comment_count
            for row in rows:
                errors = []
                if row[2] and not row[2].startswith('@'):
                    errors.append({
                        'field': 'channel_custom_url',
                        'value': str(row[2])[:50],
                        'rule': '@로 시작',
                        'reason': '@ 누락'
                    })
                if row[3] and row[3] not in ('TV', 'HHP'):
                    errors.append({
                        'field': 'category',
                        'value': str(row[3]),
                        'rule': 'TV 또는 HHP',
                        'reason': f'허용되지 않은 값: {row[3]}'
                    })
                if row[4] is not None and row[4] < 2.0:
                    errors.append({
                        'field': 'engagement_rate',
                        'value': str(row[4]),
                        'rule': '2.0 이상',
                        'reason': '기준치 미달'
                    })
                if row[5] is not None and (row[5] < -5.0 or row[5] > 5.0):
                    errors.append({
                        'field': 'product_sentiment_score',
                        'value': str(row[5]),
                        'rule': '-5.0 ~ 5.0 범위',
                        'reason': '범위 초과'
                    })
                if row[6] and row[7] and row[6] > row[7]:
                    errors.append({
                        'field': 'published_at',
                        'value': str(row[6])[:19],
                        'rule': 'published_at <= created_at',
                        'reason': '수집일보다 미래의 발행일'
                    })
                # 음수 검사 (요약 쿼리와 동일)
                if row[8] is not None and row[8] < 0:
                    errors.append({
                        'field': 'channel_subscriber_count',
                        'value': str(row[8]),
                        'rule': '0 이상',
                        'reason': '음수값'
                    })
                if row[9] is not None and row[9] < 0:
                    errors.append({
                        'field': 'channel_video_count',
                        'value': str(row[9]),
                        'rule': '0 이상',
                        'reason': '음수값'
                    })
                if row[10] is not None and row[10] < 0:
                    errors.append({
                        'field': 'view_count',
                        'value': str(row[10]),
                        'rule': '0 이상',
                        'reason': '음수값'
                    })
                if row[11] is not None and row[11] < 0:
                    errors.append({
                        'field': 'like_count',
                        'value': str(row[11]),
                        'rule': '0 이상',
                        'reason': '음수값'
                    })
                if row[12] is not None and row[12] < 0:
                    errors.append({
                        'field': 'comment_count',
                        'value': str(row[12]),
                        'rule': '0 이상',
                        'reason': '음수값'
                    })
                if errors:
                    results.append({
                        'id': row[0],  # video_id를 id로 사용
                        'video_id': row[0],
                        'keyword': row[1],
                        'channel_custom_url': row[2],
                        'category': row[3],
                        'engagement_rate': float(row[4]) if row[4] else None,
                        'product_sentiment_score': float(row[5]) if row[5] else None,
                        'errors': errors
                    })

        elif table == 'youtube_comments' or (table == 'youtube' and retailer == 'Comments'):
            # 각 레코드별 오류 검증 플래그를 SQL에서 직접 계산
            cursor.execute("""
                SELECT c.comment_id, c.video_id, c.comment_type, c.parent_comment_id, c.like_count, c.reply_count,
                       c.published_at, c.created_at,
                       CASE WHEN c.video_id IS NOT NULL AND c.video_id NOT IN (SELECT video_id FROM youtube_videos) THEN 1 ELSE 0 END as video_id_invalid,
                       CASE WHEN c.comment_type IS NOT NULL AND c.comment_type NOT IN ('top_level', 'reply') THEN 1 ELSE 0 END as comment_type_invalid,
                       CASE WHEN c.parent_comment_id IS NOT NULL AND c.parent_comment_id != '' AND c.comment_type = 'top_level' THEN 1 ELSE 0 END as parent_invalid,
                       CASE WHEN c.like_count IS NOT NULL AND c.like_count < 0 THEN 1 ELSE 0 END as like_count_invalid,
                       CASE WHEN c.reply_count IS NOT NULL AND c.reply_count < 0 THEN 1 ELSE 0 END as reply_count_invalid,
                       CASE WHEN c.published_at IS NOT NULL AND c.created_at IS NOT NULL AND c.published_at > c.created_at THEN 1 ELSE 0 END as published_at_invalid
                FROM youtube_comments c
                WHERE DATE(c.created_at) = %s
                  AND (
                      (c.video_id IS NOT NULL AND c.video_id NOT IN (SELECT video_id FROM youtube_videos))
                      OR (c.comment_type IS NOT NULL AND c.comment_type NOT IN ('top_level', 'reply'))
                      OR (c.parent_comment_id IS NOT NULL AND c.parent_comment_id != '' AND c.comment_type = 'top_level')
                      OR (c.like_count IS NOT NULL AND c.like_count < 0)
                      OR (c.reply_count IS NOT NULL AND c.reply_count < 0)
                      OR (c.published_at IS NOT NULL AND c.created_at IS NOT NULL AND c.published_at > c.created_at)
                  )
                ORDER BY c.comment_id DESC
            """, (target_date,))
            rows = cursor.fetchall()

            for row in rows:
                errors = []
                # row[8] ~ row[13]: 각 검증 플래그
                if row[8] == 1:  # video_id_invalid
                    errors.append({
                        'field': 'video_id',
                        'value': str(row[1])[:50],
                        'rule': 'youtube_videos 참조',
                        'reason': '존재하지 않는 video_id'
                    })
                if row[9] == 1:  # comment_type_invalid
                    errors.append({
                        'field': 'comment_type',
                        'value': str(row[2]),
                        'rule': 'top_level 또는 reply',
                        'reason': f'허용되지 않은 값: {row[2]}'
                    })
                if row[10] == 1:  # parent_invalid
                    errors.append({
                        'field': 'parent_comment_id',
                        'value': str(row[3])[:50],
                        'rule': 'top_level은 빈값',
                        'reason': 'top_level인데 parent 존재'
                    })
                if row[11] == 1:  # like_count_invalid
                    errors.append({
                        'field': 'like_count',
                        'value': str(row[4]),
                        'rule': '0 이상',
                        'reason': '음수값'
                    })
                if row[12] == 1:  # reply_count_invalid
                    errors.append({
                        'field': 'reply_count',
                        'value': str(row[5]),
                        'rule': '0 이상',
                        'reason': '음수값'
                    })
                if row[13] == 1:  # published_at_invalid
                    errors.append({
                        'field': 'published_at',
                        'value': str(row[6])[:19],
                        'rule': 'published_at <= created_at',
                        'reason': '수집일보다 미래의 발행일'
                    })

                if errors:
                    results.append({
                        'id': row[0],
                        'video_id': row[1],
                        'comment_type': row[2],
                        'parent_comment_id': row[3],
                        'like_count': row[4],
                        'reply_count': row[5],
                        'errors': errors
                    })

        elif table == 'market' and retailer == 'Trend':
            # market_trend 형식 오류 조회
            cursor.execute("SELECT keyword FROM market_mst WHERE analysis_type = 'trend'")
            valid_keywords = set(row[0] for row in cursor.fetchall())

            cursor.execute("""
                SELECT id, keyword, total_article_number, calendar_week, crawl_at_local_time,
                       CASE WHEN keyword IS NOT NULL AND keyword != '' THEN 1 ELSE 0 END as has_keyword,
                       CASE WHEN total_article_number IS NOT NULL THEN 1 ELSE 0 END as has_total,
                       CASE WHEN calendar_week IS NOT NULL AND calendar_week != '' THEN 1 ELSE 0 END as has_week
                FROM market_trend
                WHERE DATE(crawl_at_local_time) = %s
                  AND (
                      (keyword IS NOT NULL AND keyword != '')
                      OR (total_article_number IS NOT NULL AND total_article_number < 0)
                      OR (calendar_week IS NOT NULL AND calendar_week != '' AND calendar_week !~ '^W(0[1-9]|[1-4][0-9]|5[0-2])$')
                  )
                ORDER BY crawl_at_local_time DESC
            """, (target_date,))
            rows = cursor.fetchall()

            for row in rows:
                errors = []
                keyword = row[1]
                total_article = row[2]
                cal_week = row[3]

                # keyword가 market_mst에 없으면 오류
                if keyword and keyword not in valid_keywords:
                    errors.append({
                        'field': 'keyword',
                        'value': str(keyword)[:50],
                        'rule': 'market_mst 등록 키워드',
                        'reason': '미등록 키워드'
                    })
                # total_article_number 음수
                if total_article is not None and total_article < 0:
                    errors.append({
                        'field': 'total_article_number',
                        'value': str(total_article),
                        'rule': '0 이상',
                        'reason': '음수값'
                    })
                # calendar_week 형식 오류 (W01~W52)
                import re as re_module
                if cal_week and not re_module.match(r'^W(0[1-9]|[1-4][0-9]|5[0-2])$', cal_week):
                    errors.append({
                        'field': 'calendar_week',
                        'value': str(cal_week),
                        'rule': 'W01 ~ W52',
                        'reason': '형식 오류'
                    })

                if errors:
                    results.append({
                        'id': row[0],
                        'keyword': keyword,
                        'total_article_number': total_article,
                        'calendar_week': cal_week,
                        'errors': errors
                    })

        elif table == 'market' and retailer == 'Comp Product':
            # market_comp_product 형식 오류 조회
            cursor.execute("SELECT keyword FROM market_mst WHERE analysis_type = 'competitor' AND content_type = 'samsung'")
            valid_samsung = set(row[0] for row in cursor.fetchall())
            cursor.execute("SELECT keyword FROM market_mst WHERE analysis_type = 'competitor' AND content_type = 'comp'")
            valid_comp = set(row[0] for row in cursor.fetchall())

            cursor.execute("""
                SELECT id, samsung_series_name, comp_brand, calender_week, category, created_at
                FROM market_comp_product
                WHERE DATE(created_at) = %s
                  AND (
                      (samsung_series_name IS NOT NULL AND samsung_series_name != '')
                      OR (comp_brand IS NOT NULL AND comp_brand != '')
                      OR (calender_week IS NOT NULL AND calender_week != '' AND LOWER(calender_week) !~ '^w([1-9]|[1-4][0-9]|5[0-2])$')
                      OR (category IS NOT NULL AND category != '' AND category NOT IN ('TV', 'HHP'))
                  )
                ORDER BY created_at DESC
            """, (target_date,))
            rows = cursor.fetchall()

            for row in rows:
                errors = []
                samsung_name = row[1]
                comp_brand = row[2]
                cal_week = row[3]
                category = row[4]

                if samsung_name and samsung_name not in valid_samsung:
                    errors.append({
                        'field': 'samsung_series_name',
                        'value': str(samsung_name)[:50],
                        'rule': 'market_mst 등록',
                        'reason': '미등록 시리즈'
                    })
                if comp_brand and comp_brand not in valid_comp:
                    errors.append({
                        'field': 'comp_brand',
                        'value': str(comp_brand)[:50],
                        'rule': 'market_mst 등록',
                        'reason': '미등록 브랜드'
                    })
                import re as re_module
                if cal_week and not re_module.match(r'^[wW]([1-9]|[1-4][0-9]|5[0-2])$', cal_week):
                    errors.append({
                        'field': 'calender_week',
                        'value': str(cal_week),
                        'rule': 'w1 ~ w52',
                        'reason': '형식 오류'
                    })
                if category and category not in ('TV', 'HHP'):
                    errors.append({
                        'field': 'category',
                        'value': str(category),
                        'rule': 'TV 또는 HHP',
                        'reason': '허용되지 않은 값'
                    })

                if errors:
                    results.append({
                        'id': row[0],
                        'samsung_series_name': samsung_name,
                        'comp_brand': comp_brand,
                        'calender_week': cal_week,
                        'category': category,
                        'errors': errors
                    })

        elif table == 'market' and retailer == 'Comp Event':
            # market_comp_event 형식 오류 조회 - 최신 배치 기준
            cursor.execute("""
                SELECT comp_brand, comp_series_name FROM market_comp_product
                WHERE batch_id = (SELECT MAX(batch_id) FROM market_comp_product WHERE DATE(created_at) <= %s)
            """, (target_date,))
            latest_batch = cursor.fetchall()
            valid_comp_brands = set(row[0] for row in latest_batch if row[0])
            valid_comp_skus = set(row[1] for row in latest_batch if row[1])

            cursor.execute("""
                SELECT id, comp_brand, comp_sku_name, calender_week, category, created_at
                FROM market_comp_event
                WHERE DATE(created_at) = %s
                  AND (
                      (comp_brand IS NOT NULL AND comp_brand != '')
                      OR (comp_sku_name IS NOT NULL AND comp_sku_name != '')
                      OR (calender_week IS NOT NULL AND calender_week != '' AND LOWER(calender_week) !~ '^w([1-9]|[1-4][0-9]|5[0-2])$')
                      OR (category IS NOT NULL AND category != '' AND category NOT IN ('TV', 'HHP'))
                  )
                ORDER BY created_at DESC
            """, (target_date,))
            rows = cursor.fetchall()

            for row in rows:
                errors = []
                comp_brand = row[1]
                comp_sku = row[2]
                cal_week = row[3]
                category = row[4]

                if comp_brand and comp_brand not in valid_comp_brands:
                    errors.append({
                        'field': 'comp_brand',
                        'value': str(comp_brand)[:50],
                        'rule': 'market_comp_product 참조',
                        'reason': '미등록 브랜드'
                    })
                if comp_sku and comp_sku not in valid_comp_skus:
                    errors.append({
                        'field': 'comp_sku_name',
                        'value': str(comp_sku)[:50],
                        'rule': 'market_comp_product 참조',
                        'reason': '미등록 SKU'
                    })
                import re as re_module
                if cal_week and not re_module.match(r'^[wW]([1-9]|[1-4][0-9]|5[0-2])$', cal_week):
                    errors.append({
                        'field': 'calender_week',
                        'value': str(cal_week),
                        'rule': 'w1 ~ w52',
                        'reason': '형식 오류'
                    })
                if category and category not in ('TV', 'HHP'):
                    errors.append({
                        'field': 'category',
                        'value': str(category),
                        'rule': 'TV 또는 HHP',
                        'reason': '허용되지 않은 값'
                    })

                if errors:
                    results.append({
                        'id': row[0],
                        'comp_brand': comp_brand,
                        'comp_sku_name': comp_sku,
                        'calender_week': cal_week,
                        'category': category,
                        'errors': errors
                    })

        elif table == 'market' and retailer == 'Forecast':
            # openai_forecast_results 형식 오류 조회
            cursor.execute("SELECT product_name FROM openai_keywords WHERE is_active = true")
            valid_products = set(row[0] for row in cursor.fetchall())
            cursor.execute("SELECT LOWER(REPLACE(event_name, ' ', '_')) FROM openai_event_mst WHERE is_active = true")
            valid_events = set(row[0] for row in cursor.fetchall())

            cursor.execute("""
                SELECT id, product_name, event, metric_type, event_offset, event_value, week, crawled_at
                FROM openai_forecast_results
                WHERE DATE(crawled_at) = %s
                  AND (
                      (product_name IS NOT NULL AND product_name != '')
                      OR (event IS NOT NULL AND event != '')
                      OR (metric_type IS NOT NULL AND metric_type != '' AND metric_type != 'Forecasted_NA_sales_change')
                      OR (event_offset IS NOT NULL AND (event_offset < 0 OR event_offset > 9))
                      OR (event_value IS NOT NULL AND event_value::text !~ '^-?[0-9]+\.?[0-9]*$')
                      OR (week IS NOT NULL AND week != '' AND week !~ '^w[0-9]{1,2}$')
                      OR (crawled_at IS NOT NULL AND crawled_at::text !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$')
                  )
                ORDER BY crawled_at DESC
                LIMIT 100
            """, (target_date,))
            rows = cursor.fetchall()

            import re as re_module
            for row in rows:
                errors = []
                product_name = row[1]
                event = row[2]
                metric_type = row[3]
                event_offset = row[4]
                event_value = row[5]
                week = row[6]
                crawled_at = row[7]

                if product_name and product_name not in valid_products:
                    errors.append({
                        'field': 'product_name',
                        'value': str(product_name)[:50],
                        'rule': 'openai_keywords 등록',
                        'reason': '미등록 제품'
                    })
                if event and event.lower().replace(' ', '_') not in valid_events:
                    errors.append({
                        'field': 'event',
                        'value': str(event)[:50],
                        'rule': 'openai_event_mst 등록',
                        'reason': '미등록 이벤트'
                    })
                if metric_type and metric_type != 'Forecasted_NA_sales_change':
                    errors.append({
                        'field': 'metric_type',
                        'value': str(metric_type)[:50],
                        'rule': 'Forecasted_NA_sales_change',
                        'reason': '허용되지 않은 값'
                    })
                if event_offset is not None and (event_offset < 0 or event_offset > 9):
                    errors.append({
                        'field': 'event_offset',
                        'value': str(event_offset),
                        'rule': '0 ~ 9',
                        'reason': '범위 초과'
                    })
                if event_value is not None and not re_module.match(r'^-?[0-9]+\.?[0-9]*$', str(event_value)):
                    errors.append({
                        'field': 'event_value',
                        'value': str(event_value)[:30],
                        'rule': '숫자 형식',
                        'reason': '형식 오류'
                    })
                if week and not re_module.match(r'^w[0-9]{1,2}$', week):
                    errors.append({
                        'field': 'week',
                        'value': str(week),
                        'rule': 'w + 숫자',
                        'reason': '형식 오류'
                    })
                if crawled_at and not re_module.match(r'^[0-9]{4}-[0-9]{2}-[0-9]{2}$', str(crawled_at)):
                    errors.append({
                        'field': 'crawled_at',
                        'value': str(crawled_at)[:20],
                        'rule': 'YYYY-MM-DD',
                        'reason': '형식 오류'
                    })

                if errors:
                    results.append({
                        'id': row[0],
                        'product_name': product_name,
                        'event': event,
                        'metric_type': metric_type,
                        'event_offset': event_offset,
                        'event_value': event_value,
                        'week': week,
                        'errors': errors
                    })

        cursor.close()
        conn.close()

        return JsonResponse({
            'date': str(target_date),
            'table': table,
            'retailer': retailer,
            'results': results
        })

    except Exception as e:
        return JsonResponse({'error': str(e)})


def anomaly_detail(request):
    """중복 검증 상세 조회 API - 리테일러별, 시간대별 중복 상세"""
    date_str = request.GET.get('date')
    table = request.GET.get('table', 'tv_retail')
    retailer = request.GET.get('retailer', '')
    page = int(request.GET.get('page', 1))
    page_size = int(request.GET.get('page_size', 50))

    if date_str:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    else:
        target_date = (datetime.now() - timedelta(days=1)).date()

    try:
        conn = get_dx_connection()
        cursor = conn.cursor()

        duplicates = []

        if table == 'tv_retail':
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
                )
                SELECT d.item, d.account_name, d.period, d.dup_count,
                       t.id, t.product_url, t.crawl_datetime, t.page_type, t.main_rank, t.bsr_rank
                FROM duplicate_groups d
                JOIN tv_retail_com t ON t.item IS NOT DISTINCT FROM d.item
                    AND t.account_name = d.account_name
                    AND DATE(t.crawl_datetime::timestamp) = %s
                    AND CASE WHEN EXTRACT(HOUR FROM t.crawl_datetime::timestamp) < 12 THEN '오전' ELSE '오후' END = d.period
                ORDER BY d.dup_count DESC, d.item, d.period, t.crawl_datetime
                LIMIT 200
            """, (target_date, retailer, retailer, target_date))

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
                )
                SELECT d.item, d.account_name, d.period, d.dup_count,
                       h.id, h.product_url, h.crawl_strdatetime, h.page_type, h.main_rank, h.bsr_rank, h.trend_rank
                FROM duplicate_groups d
                JOIN hhp_retail_com h ON h.item IS NOT DISTINCT FROM d.item
                    AND h.account_name = d.account_name
                    AND DATE(h.crawl_strdatetime::timestamp) = %s
                    AND CASE WHEN EXTRACT(HOUR FROM h.crawl_strdatetime::timestamp) < 12 THEN '오전' ELSE '오후' END = d.period
                ORDER BY d.dup_count DESC, d.item, d.period, h.crawl_strdatetime
                LIMIT 200
            """, (target_date, retailer, retailer, target_date))

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
            # YouTube Videos 중복 그룹 찾기: video_id + keyword
            cursor.execute("""
                WITH duplicate_groups AS (
                    SELECT video_id, keyword, COUNT(*) as dup_count
                    FROM youtube_videos
                    WHERE DATE(created_at) = %s
                    GROUP BY video_id, keyword
                    HAVING COUNT(*) > 1
                )
                SELECT d.video_id, d.keyword, d.dup_count,
                       y.id, y.title, y.created_at
                FROM duplicate_groups d
                JOIN youtube_videos y ON y.video_id = d.video_id
                    AND y.keyword = d.keyword
                    AND DATE(y.created_at) = %s
                ORDER BY d.dup_count DESC, d.video_id, d.keyword, y.created_at
            """, (target_date, target_date))

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
            # YouTube Logs 중복 그룹 찾기: keyword + category (조인 필요)
            cursor.execute("""
                WITH duplicate_groups AS (
                    SELECT k.keyword, k.category, COUNT(*) as dup_count
                    FROM youtube_collection_logs l
                    JOIN youtube_keywords k ON l.keyword_id = k.id
                    WHERE DATE(l.started_at) = %s
                    GROUP BY k.keyword, k.category
                    HAVING COUNT(*) > 1
                )
                SELECT d.keyword, d.category, d.dup_count,
                       l.id, l.started_at
                FROM duplicate_groups d
                JOIN youtube_keywords k ON k.keyword = d.keyword AND k.category = d.category
                JOIN youtube_collection_logs l ON l.keyword_id = k.id
                    AND DATE(l.started_at) = %s
                ORDER BY d.dup_count DESC, d.keyword, d.category, l.started_at
            """, (target_date, target_date))

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
            # Market Trend 중복: 같은 날짜에 keyword 중복
            cursor.execute("""
                WITH duplicate_groups AS (
                    SELECT keyword, COUNT(*) as dup_count
                    FROM market_trend
                    WHERE DATE(crawl_at_local_time) = %s
                    GROUP BY keyword
                    HAVING COUNT(*) > 1
                )
                SELECT d.keyword, d.dup_count,
                       m.id, m.total_article_number, m.crawl_at_local_time
                FROM duplicate_groups d
                JOIN market_trend m ON m.keyword = d.keyword
                    AND DATE(m.crawl_at_local_time) = %s
                ORDER BY d.dup_count DESC, d.keyword, m.crawl_at_local_time
            """, (target_date, target_date))

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
            # Market Product 중복: batch_id + samsung_series_name + comp_brand + comp_series_name
            cursor.execute("""
                WITH duplicate_groups AS (
                    SELECT batch_id, samsung_series_name, comp_brand, comp_series_name, COUNT(*) as dup_count
                    FROM market_comp_product
                    WHERE DATE(created_at) = %s
                    GROUP BY batch_id, samsung_series_name, comp_brand, comp_series_name
                    HAVING COUNT(*) > 1
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
                LIMIT 500
            """, (target_date, target_date))

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
            # Market Event 중복: batch_id + comp_brand + comp_sku_name
            cursor.execute("""
                WITH duplicate_groups AS (
                    SELECT batch_id, comp_brand, comp_sku_name, COUNT(*) as dup_count
                    FROM market_comp_event
                    WHERE DATE(created_at) = %s
                    GROUP BY batch_id, comp_brand, comp_sku_name
                    HAVING COUNT(*) > 1
                )
                SELECT d.batch_id, d.comp_brand, d.comp_sku_name, d.dup_count,
                       m.id, m.created_at
                FROM duplicate_groups d
                JOIN market_comp_event m ON m.batch_id = d.batch_id
                    AND m.comp_brand = d.comp_brand
                    AND m.comp_sku_name = d.comp_sku_name
                    AND DATE(m.created_at) = %s
                ORDER BY d.dup_count DESC, d.batch_id, d.comp_brand, m.created_at
                LIMIT 500
            """, (target_date, target_date))

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

        cursor.close()
        conn.close()

        return JsonResponse({
            'date': str(target_date),
            'table': table,
            'retailer': retailer,
            'results': {'duplicates': duplicates}
        })

    except Exception as e:
        return JsonResponse({'error': str(e)})


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

    date_str = request.GET.get('date')

    if date_str:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    else:
        target_date = (datetime.now() - timedelta(days=1)).date()

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
                    'error': str(e)
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
                    'error': str(e)
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
                    'error': str(e)
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

        cursor.close()
        conn.close()

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
        results['error'] = str(e)
        results['summary']['overall_status'] = 'ERROR'

    return JsonResponse(results)


def retailer_detail(request):
    """리테일러별 상세 오류 데이터 조회 API"""
    validation_type = request.GET.get('type', 'null')  # null, format, anomaly
    table_name = request.GET.get('table', '')  # TV Retail, HHP Retail
    retailer = request.GET.get('retailer', '')
    date_str = request.GET.get('date')

    if date_str:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    else:
        target_date = (datetime.now() - timedelta(days=1)).date()

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
        if 'TV' in table_name:
            db_table = 'tv_retail_com'
            date_field = 'crawl_datetime'
            null_fields = ['item', 'screen_size', 'final_sku_price', 'retailer_sku_name',
                          'count_of_reviews', 'star_rating', 'count_of_star_ratings']
        elif 'HHP' in table_name:
            db_table = 'hhp_retail_com'
            date_field = 'crawl_strdatetime'
            null_fields = ['item', 'final_sku_price', 'retailer_sku_name',
                          'count_of_reviews', 'star_rating', 'count_of_star_ratings']
        else:
            return JsonResponse({'error': 'Invalid table name'}, status=400)

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
            if 'TV' in table_name:
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
        results['error'] = str(e)

    return JsonResponse(results)


def get_tv_format_errors(cursor, table_name, date_field, target_date, retailer):
    """TV 형식 오류 데이터 조회"""
    errors = []

    # main_rank 검증 (1-400 범위)
    cursor.execute(f"""
        SELECT id, item, main_rank, {date_field}
        FROM {table_name}
        WHERE DATE({date_field}::timestamp) = %s
          AND account_name = %s
          AND main_rank IS NOT NULL
          AND main_rank != ''
          AND (
              NOT main_rank ~ '^[0-9]+$'
              OR CAST(main_rank AS INTEGER) < 1
              OR CAST(main_rank AS INTEGER) > 400
          )
        LIMIT 50
    """, (target_date, retailer))

    for row in cursor.fetchall():
        errors.append({
            'id': row[0],
            'item': row[1],
            'error_field': 'main_rank',
            'error_value': str(row[2]),
            'collected_at': str(row[3]) if row[3] else None
        })

    # star_rating 검증 (0.0-5.0)
    cursor.execute(f"""
        SELECT id, item, star_rating, {date_field}
        FROM {table_name}
        WHERE DATE({date_field}::timestamp) = %s
          AND account_name = %s
          AND star_rating IS NOT NULL
          AND star_rating != ''
          AND (
              NOT star_rating ~ '^[0-9]+(\\.[0-9]+)?$'
              OR CAST(star_rating AS NUMERIC) < 0
              OR CAST(star_rating AS NUMERIC) > 5
          )
        LIMIT 50
    """, (target_date, retailer))

    for row in cursor.fetchall():
        errors.append({
            'id': row[0],
            'item': row[1],
            'error_field': 'star_rating',
            'error_value': str(row[2]),
            'collected_at': str(row[3]) if row[3] else None
        })

    return errors


def get_hhp_format_errors(cursor, table_name, date_field, target_date, retailer):
    """HHP 형식 오류 데이터 조회"""
    errors = []

    # main_rank 검증 (1-300 범위)
    cursor.execute(f"""
        SELECT id, item, main_rank, {date_field}
        FROM {table_name}
        WHERE DATE({date_field}::timestamp) = %s
          AND account_name = %s
          AND main_rank IS NOT NULL
          AND main_rank != ''
          AND (
              NOT main_rank ~ '^[0-9]+$'
              OR CAST(main_rank AS INTEGER) < 1
              OR CAST(main_rank AS INTEGER) > 300
          )
        LIMIT 50
    """, (target_date, retailer))

    for row in cursor.fetchall():
        errors.append({
            'id': row[0],
            'item': row[1],
            'error_field': 'main_rank',
            'error_value': str(row[2]),
            'collected_at': str(row[3]) if row[3] else None
        })

    # star_rating 검증 (0.0-5.0)
    cursor.execute(f"""
        SELECT id, item, star_rating, {date_field}
        FROM {table_name}
        WHERE DATE({date_field}::timestamp) = %s
          AND account_name = %s
          AND star_rating IS NOT NULL
          AND star_rating != ''
          AND (
              NOT star_rating ~ '^[0-9]+(\\.[0-9]+)?$'
              OR CAST(star_rating AS NUMERIC) < 0
              OR CAST(star_rating AS NUMERIC) > 5
          )
        LIMIT 50
    """, (target_date, retailer))

    for row in cursor.fetchall():
        errors.append({
            'id': row[0],
            'item': row[1],
            'error_field': 'star_rating',
            'error_value': str(row[2]),
            'collected_at': str(row[3]) if row[3] else None
        })

    return errors


def format_rules(request):
    """형식검증 규칙 조회 API - CSV 기반"""
    table_name = request.GET.get('table', 'tv_retail_com')
    retailer = request.GET.get('retailer', 'Amazon')

    # 테이블명 → product_line 매핑
    table_to_product = {
        'tv_retail_com': 'TV',
        'hhp_retail_com': 'HHP',
    }
    product_line = table_to_product.get(table_name, 'ALL')

    rules_data = load_format_rules()
    result = []

    if table_name not in rules_data:
        return JsonResponse({'rules': []})

    table_rules = rules_data[table_name]

    # 해당 product_line 규칙 수집
    if product_line in table_rules:
        for column_name, column_rules in table_rules[product_line].items():
            result.extend(_format_rules_for_display(column_name, column_rules, retailer))

    # ALL 규칙도 추가 (product_line이 ALL이 아닌 경우)
    if product_line != 'ALL' and 'ALL' in table_rules:
        for column_name, column_rules in table_rules['ALL'].items():
            result.extend(_format_rules_for_display(column_name, column_rules, retailer))

    # 필드명 기준 정렬 및 중복 제거
    seen = set()
    unique_result = []
    for rule in result:
        key = (rule['field'], rule['description'])
        if key not in seen:
            seen.add(key)
            unique_result.append(rule)

    # 필드명 알파벳순 정렬
    unique_result.sort(key=lambda x: x['field'])

    return JsonResponse({'rules': unique_result})


def _format_rules_for_display(column_name, column_rules, retailer):
    """CSV 규칙을 프론트엔드 표시용 형식으로 변환"""
    result = []

    # 리테일러별 규칙과 common 규칙 분리
    retailer_rules = [r for r in column_rules if r['retailer'] == retailer]
    common_rules = [r for r in column_rules if r['retailer'] == 'common']

    # 규칙 병합하여 표시
    patterns = []
    description = ''

    # common 규칙에서 기본 description 추출
    for rule in common_rules:
        rule_type = rule['type']
        rule_value = rule['rule']
        allowed = rule['allowed']
        error_msg = rule.get('error', '')

        if rule_type == 'regex':
            patterns.append(rule_value)
            description = error_msg or _get_description_for_type(rule_type, rule_value, allowed)
        elif rule_type == 'regex_clean':
            patterns.append(rule_value)
            clean_type = allowed[0] if allowed else ''
            description = error_msg or f'숫자 ({clean_type.replace("_", ", ")} 허용)'
        elif rule_type == 'range':
            parts = rule_value.split('~')
            patterns.append(f'{parts[0]} ~ {parts[1]}')
            description = error_msg or f'{parts[0]}~{parts[1]} 범위 정수'
        elif rule_type == 'range_float':
            parts = rule_value.split('~')
            patterns.append(f'{parts[0]} ~ {parts[1]}')
            description = error_msg or f'{parts[0]}~{parts[1]} 범위'
        elif rule_type == 'enum':
            patterns.append(' | '.join(allowed))
            description = error_msg or '허용값만'
        elif rule_type == 'starts_with':
            patterns.append(f'"{rule_value}..."')
            description = error_msg or f'{rule_value}로 시작'
        elif rule_type == 'separator_count':
            parts = rule_value.split('~')
            patterns.append(f'{parts[0]} 구분자 {parts[1]}개')
            description = error_msg or f'{parts[0]} 구분자 {parts[1]}개 필요'
        elif rule_type == 'fk_check':
            # FK 참조 검증 (예: market_mst.keyword|analysis_type=competitor)
            patterns.append(f'참조: {rule_value}')
            description = error_msg or 'FK 참조 검증'
        elif rule_type == 'min':
            patterns.append(f'>= {rule_value}')
            description = error_msg or f'{rule_value} 이상'

    # 리테일러별 allowed_values 추가
    for rule in retailer_rules:
        if rule['type'] == 'allowed_values' and rule['allowed']:
            for val in rule['allowed']:
                patterns.append(f'"{val}"')
            if not description:
                description = '허용값만'
        elif rule['type'] == 'starts_with':
            patterns.append(f'"{rule["rule"]}..."')
            if not description:
                description = f'{rule["rule"]}로 시작'
        elif rule['type'] == 'regex':
            patterns.append(rule['rule'])
            if not description:
                description = _get_description_for_type('regex', rule['rule'], rule['allowed'])

    if patterns:
        result.append({
            'field': column_name,
            'description': description or '형식 검증',
            'pattern': '\n'.join(patterns)
        })

    return result


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
