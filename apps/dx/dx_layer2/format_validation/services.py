"""
형식 검증 서비스 — 순수 비즈니스 로직 (DB 커넥션/HTTP 무관)
"""

import re
from datetime import datetime, timedelta

from apps.common.retail_columns import (
    validate_field,
    build_format_error_sql,
    build_per_field_error_sql,
    get_editable_columns,
)
from apps.common.db import dx_table
from apps.common.sea_retail import SEA_RETAIL_TABLES
from apps.dx.dx_layer2.common.context import get_status


# table 파라미터 화이트리스트
VALID_TABLES_FORMAT = {
    'tv_retail',
    'ref_retail', 'ldy_retail',
    'youtube_logs', 'youtube_videos', 'youtube_comments', 'youtube',
    'market',
}
VALID_TABLES_RULES = {
    'tv_retail_com',
    'ref_retail_com', 'ldy_retail_com',
    'youtube_collection_logs', 'youtube_videos', 'youtube_comments',
    'market_trend', 'market_comp_product', 'market_comp_event',
    'openai_forecast_results',
}

SEA_FORMAT_FIELDS = [
    'account_name',
    'product',
    'page_type',
    'product_url',
    'star_rating',
    'count_of_reviews',
    'count_of_star_ratings',
    'final_sku_price',
    'original_sku_price',
    'savings',
    'main_rank',
    'bsr_rank',
    'calendar_week',
    'crawl_strdatetime',
    'number_of_units_purchased_past_week',
]

SEA_DETAIL_FIELDS = [
    'item',
    'account_name',
    'product',
    'page_type',
    'product_url',
    'main_rank',
    'bsr_rank',
    'count_of_reviews',
    'star_rating',
    'count_of_star_ratings',
    'final_sku_price',
    'original_sku_price',
    'savings',
    'calendar_week',
    'number_of_units_purchased_past_week',
]


# ── thin wrappers ──────────────────────────────────────────

def validate_tv_field(field_name, value, account_name='Amazon'):
    """TV Retail 필드별 형식 검증. 오류 시 메시지 반환, 정상이면 None"""
    return validate_field('tv_retail_com', field_name, value, account_name, product_line='TV')


def validate_hhp_field(field_name, value, account_name='Amazon'):
    """HHP Retail 필드별 형식 검증. 오류 시 메시지 반환, 정상이면 None"""
    return validate_field('hhp_retail_com', field_name, value, account_name, product_line='HHP')


def _format_error(field_name, reason):
    return f'{field_name}: {reason}'


def _is_blank(value):
    return value is None or str(value).strip() == ''


def _is_integer_like(value):
    return re.fullmatch(r'\d{1,3}(,\d{3})*|\d+', str(value).strip()) is not None


def _is_price_like(value):
    val = str(value).strip()
    return re.fullmatch(r'\$?\s*\d{1,3}(,\d{3})*(\.\d+)?|\$?\s*\d+(\.\d+)?', val) is not None


def _is_savings_like(value):
    val = str(value).strip()
    return bool(re.search(r'\d', val)) and re.fullmatch(r'[A-Za-z0-9\s$%,.\-+]+', val) is not None


def _is_datetime_like(value):
    val = str(value).strip().replace('T', ' ')
    try:
        datetime.fromisoformat(val)
        return True
    except ValueError:
        return False


def validate_sea_retail_field(product_line, field_name, value, account_name=None):
    """REF/LDY Retail format validation using DB rules first, then baseline rules."""
    config = SEA_RETAIL_TABLES.get(product_line)
    if not config or _is_blank(value):
        return None

    table_name = config['table']
    product_key = product_line.upper()
    db_error = validate_field(table_name, field_name, value, account_name or 'ALL', product_line=product_key)
    if db_error:
        return db_error

    val = str(value).strip()

    if field_name == 'account_name':
        if val not in config['retailers']:
            return _format_error(field_name, f"allowed: {', '.join(config['retailers'])}")
    elif field_name == 'product':
        if val.upper() != product_key:
            return _format_error(field_name, f'allowed: {product_key}')
    elif field_name == 'page_type':
        if val not in ('main', 'bsr'):
            return _format_error(field_name, 'allowed: main, bsr')
    elif field_name == 'product_url':
        if not re.match(r'^https?://', val):
            return _format_error(field_name, 'URL must start with http:// or https://')
    elif field_name == 'star_rating':
        if account_name == 'Bestbuy' and val == 'Not yet reviewed':
            return None
        rating_match = re.search(r'\d+(\.\d+)?', val)
        try:
            rating = float(rating_match.group(0)) if rating_match else float(val)
            if rating < 0 or rating > 5:
                return _format_error(field_name, '0~5 range')
        except (ValueError, AttributeError):
            return _format_error(field_name, 'numeric')
    elif field_name in ('count_of_reviews', 'count_of_star_ratings', 'main_rank', 'bsr_rank'):
        if not _is_integer_like(val):
            return _format_error(field_name, 'integer')
    elif field_name in ('final_sku_price', 'original_sku_price'):
        if not _is_price_like(val):
            return _format_error(field_name, 'price format')
    elif field_name == 'savings':
        if not _is_savings_like(val):
            return _format_error(field_name, 'savings format')
    elif field_name == 'calendar_week':
        if not re.search(r'\d', val) or len(val) > 20:
            return _format_error(field_name, 'calendar week format')
    elif field_name == 'crawl_strdatetime':
        if not _is_datetime_like(val):
            return _format_error(field_name, 'datetime format')
    elif field_name == 'number_of_units_purchased_past_week':
        if account_name == 'Lowes' and not re.search(r'\bbought last week$', val, re.IGNORECASE):
            return _format_error(field_name, 'must end with bought last week')

    return None


def _split_error(error):
    if ':' in error:
        rule, reason = error.split(':', 1)
        return rule, reason.strip()
    return error, error


def _build_sea_retail_record(product_line, row, fields):
    record_id = row[0]
    crawl_dt = row[1]
    values = list(row[2:])
    record = {
        'id': record_id,
        'crawl_datetime': str(crawl_dt) if crawl_dt else None,
        'crawl_strdatetime': str(crawl_dt) if crawl_dt else None,
    }
    for field, value in zip(fields, values):
        record[field] = str(value) if value is not None else None

    account_name = record.get('account_name')
    error_fields = []
    error_details = {}
    validation_values = dict(record)
    validation_values['crawl_strdatetime'] = record.get('crawl_strdatetime')

    for field in SEA_FORMAT_FIELDS:
        error = validate_sea_retail_field(product_line, field, validation_values.get(field), account_name)
        if error:
            rule, reason = _split_error(error)
            error_fields.append(field)
            error_details[field] = {'rule': rule, 'reason': reason}

    record['error_fields'] = error_fields
    record['error_details'] = error_details
    return record


def _get_sea_retail_format_detail(cursor, target_date, table, retailer, days):
    product_line = table.replace('_retail', '')
    config = SEA_RETAIL_TABLES[product_line]
    db_table = config['table']
    date_col = config['date_column']
    fields = SEA_DETAIL_FIELDS
    column_names = ['id', 'crawl_datetime', 'crawl_strdatetime'] + fields

    next_date = target_date + timedelta(days=1)
    params = [str(target_date), str(next_date)]
    retailer_filter = ''
    if retailer:
        retailer_filter = ' AND account_name = %s'
        params.append(retailer)

    cursor.execute(f"""
        SELECT id, {date_col}, {', '.join(fields)}
        FROM {db_table}
        WHERE {date_col}::timestamp >= %s AND {date_col}::timestamp < %s
        {retailer_filter}
        ORDER BY account_name, {date_col}
    """, params)

    results = []
    for row in cursor.fetchall():
        record = _build_sea_retail_record(product_line, row, fields)
        if record['error_fields']:
            results.append(record)

    if days > 1 and results:
        error_items = sorted({r['item'] for r in results if r.get('item')})
        if error_items:
            start_date = target_date - timedelta(days=days - 1)
            placeholders = ', '.join(['%s'] * len(error_items))
            params = [str(start_date), str(next_date)]
            retailer_filter = ''
            if retailer:
                retailer_filter = ' AND account_name = %s'
                params.append(retailer)
            params.extend(error_items)
            cursor.execute(f"""
                SELECT id, {date_col}, {', '.join(fields)}
                FROM {db_table}
                WHERE {date_col}::timestamp >= %s AND {date_col}::timestamp < %s
                {retailer_filter}
                  AND item IN ({placeholders})
                ORDER BY item, {date_col}
            """, params)
            results = [_build_sea_retail_record(product_line, row, fields) for row in cursor.fetchall()]

    return results, column_names


def _get_sea_retail_format_stats_table(cursor, target_date, product_line):
    config = SEA_RETAIL_TABLES[product_line]
    db_table = config['table']
    date_col = config['date_column']
    table_key = f'{product_line}_retail'
    table_name = f'{product_line.upper()} Retail'

    errors_sample = []
    issue_by_retailer = {retailer: 0 for retailer in config['retailers']}
    total_by_retailer = {retailer: 0 for retailer in config['retailers']}
    rows_count = 0

    cursor.execute(f"""
        SELECT id, {date_col}, {', '.join(SEA_DETAIL_FIELDS)}
        FROM {db_table}
        WHERE DATE({date_col}::timestamp) = %s
        ORDER BY account_name, id
    """, (target_date,))

    for row in cursor.fetchall():
        rows_count += 1
        record = _build_sea_retail_record(product_line, row, SEA_DETAIL_FIELDS)
        account_name = record.get('account_name') or 'Unknown'
        total_by_retailer[account_name] = total_by_retailer.get(account_name, 0) + 1
        errors = []
        for field in record.get('error_fields', []):
            detail = record.get('error_details', {}).get(field, {})
            errors.append({
                'field': field,
                'value': str(record.get(field) or '')[:30],
                'error': detail.get('reason') or detail.get('rule') or field,
            })

        if errors:
            if len(errors_sample) < 30:
                errors_sample.append({
                    'id': record.get('id'),
                    'account_name': account_name,
                    'item': record.get('item'),
                    'errors': errors[:5],
                })
            issue_by_retailer[account_name] = issue_by_retailer.get(account_name, 0) + len(errors)

    retailers = []
    issue_total = 0
    for retailer in config['retailers']:
        count = issue_by_retailer.get(retailer, 0)
        retailers.append({
            'retailer': retailer,
            'total': total_by_retailer.get(retailer, 0),
            'issue_count': count,
            'status': get_status(count),
        })
        issue_total += count

    return {
        'table': table_key,
        'table_name': table_name,
        'total_checked': rows_count,
        'total_issues': issue_total,
        'status': get_status(issue_total),
        'retailers': retailers,
        'sample_errors': errors_sample,
    }, issue_total


# ── 형식 오류 상세 조회 ───────────────────────────────────

def get_format_detail(cursor, target_date, table, retailer, days):
    """
    형식 오류 상세 조회.
    Returns dict: {date, table, retailer, column_names, editable_cols, actual_table, normal_reviews, results}
    """
    results = []
    select_cols = []
    column_names = []
    next_date = target_date + timedelta(days=1)
    if table == 'hhp_retail':
        return {
            'date': str(target_date),
            'table': table,
            'retailer': retailer,
            'column_names': [],
            'editable_cols': [],
            'actual_table': '',
            'normal_reviews': {},
            'results': []
        }

    # TV Retail 형식 오류 상세 조회 - SQL 조건으로 오류 행 직접 필터링
    if table in ('ref_retail', 'ldy_retail'):
        results, column_names = _get_sea_retail_format_detail(cursor, target_date, table, retailer, days)

    elif table == 'tv_retail':
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
                        'rule': error.split(':', 1)[0] if ':' in error else error,
                        'reason': error.split(':', 1)[1].strip() if ':' in error else error
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
            'number_of_units_purchased_past_month', 'available_quantity_for_purchase', 'delivery_availability',
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
                        'rule': error.split(':', 1)[0] if ':' in error else error,
                        'reason': error.split(':', 1)[1].strip() if ':' in error else error
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
                                'rule': error.split(':', 1)[0] if ':' in error else error,
                                'reason': error.split(':', 1)[1].strip() if ':' in error else error
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
                        number_of_units_purchased_past_month, available_quantity_for_purchase, delivery_availability,
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
                    'number_of_units_purchased_past_month', 'available_quantity_for_purchase', 'delivery_availability',
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
                                'rule': error.split(':', 1)[0] if ':' in error else error,
                                'reason': error.split(':', 1)[1].strip() if ':' in error else error
                            }
                    record['error_fields'] = error_fields
                    record['error_details'] = error_details
                    results.append(record)

    # 수정 가능 컬럼 + actual_table 설정
    editable_cols = []
    actual_table = ''
    if table in ('tv_retail', 'ref_retail', 'ldy_retail', 'hhp_retail') and retailer:
        product_line = table.replace('_retail', '')
        actual_table = SEA_RETAIL_TABLES.get(product_line, {}).get('table') or (
            'hhp_retail_com' if table == 'hhp_retail' else 'tv_retail_com'
        )
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

    # 필드별 건수 집계 (프론트에서 재계산하지 않도록 백엔드에서 계산)
    field_counts = {}
    total_format_count = 0
    for record in results:
        for field in record.get('error_fields', []):
            field_counts[field] = field_counts.get(field, 0) + 1
            total_format_count += 1

    return {
        'date': str(target_date),
        'table': table,
        'retailer': retailer,
        'column_names': column_names,
        'editable_cols': editable_cols,
        'actual_table': actual_table,
        'normal_reviews': normal_reviews,
        'results': results,
        'field_counts': field_counts,
        'total_format_count': total_format_count,
    }


# ── 형식 검증 규칙 조회 ──────────────────────────────────

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


def _sea_baseline_format_rules(table_name, retailer):
    product_line = None
    for key, config in SEA_RETAIL_TABLES.items():
        if config['table'] == table_name:
            product_line = key
            break
    if product_line not in ('ref', 'ldy'):
        return []

    config = SEA_RETAIL_TABLES[product_line]
    return [
        {'field': 'account_name', 'description': 'retailer enum', 'pattern': ' | '.join(config['retailers'])},
        {'field': 'product', 'description': 'product enum', 'pattern': product_line.upper()},
        {'field': 'page_type', 'description': 'page type enum', 'pattern': 'main | bsr'},
        {'field': 'product_url', 'description': 'URL format', 'pattern': 'http://... | https://...'},
        {'field': 'star_rating', 'description': 'numeric range', 'pattern': '0 ~ 5'},
        {'field': 'count_of_reviews', 'description': 'integer', 'pattern': '0 or greater'},
        {'field': 'count_of_star_ratings', 'description': 'integer', 'pattern': '0 or greater'},
        {'field': 'final_sku_price', 'description': 'price format', 'pattern': '$1,234.56'},
        {'field': 'original_sku_price', 'description': 'price format', 'pattern': '$1,234.56'},
        {'field': 'savings', 'description': 'savings amount/rate text', 'pattern': 'contains numeric amount or rate'},
        {'field': 'main_rank', 'description': 'integer', 'pattern': '0 or greater'},
        {'field': 'bsr_rank', 'description': 'integer', 'pattern': '0 or greater'},
        {'field': 'calendar_week', 'description': 'calendar week format', 'pattern': 'contains week number'},
        {'field': 'crawl_strdatetime', 'description': 'datetime format', 'pattern': 'YYYY-MM-DD HH:MM:SS'},
        {'field': 'number_of_units_purchased_past_week', 'description': 'Lowes purchase badge text', 'pattern': '* bought last week'},
    ]


def get_format_rules(cursor, table_name, retailer):
    """
    형식검증 규칙 조회.
    Returns dict: {rules: [...]}
    """
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
    existing_fields = {rule['field'] for rule in result}
    for rule in _sea_baseline_format_rules(table_name, retailer):
        if rule['field'] not in existing_fields:
            result.append(rule)

    result.sort(key=lambda x: x['field'])

    return {'rules': result}


# ── 대시보드용 헬퍼 / 통계 ─────────────────────────────────

def get_tv_format_errors(cursor, table_name, date_field, target_date, retailer):
    """TV 형식 오류 데이터 조회 - validate_tv_field 기반"""
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
            page_type, main_rank, bsr_rank,
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
        values = [item] + list(row[4:])
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
    """HHP 형식 오류 데이터 조회 - validate_hhp_field 기반"""
    errors = []
    hhp_fields = [
        'item', 'page_type', 'product_url', 'main_rank', 'bsr_rank', 'trend_rank',
        'final_sku_price', 'original_sku_price',
        'count_of_reviews', 'star_rating', 'count_of_star_ratings',
        'detailed_review_content', 'trade_in', 'sku_status',
        'number_of_units_purchased_past_month', 'available_quantity_for_purchase', 'delivery_availability',
        'sku_popularity', 'retailer_membership_discounts',
        'rank_1', 'rank_2', 'summarized_review_content',
        'savings', 'offer', 'retailer_sku_name_similar', 'recommendation_intent',
        'number_of_ppl_purchased_yesterday', 'number_of_ppl_added_to_carts', 'discount_type'
    ]
    cursor.execute(f"""
        SELECT
            id, item, {date_field}, product_url,
            page_type, main_rank, bsr_rank, trend_rank,
            final_sku_price, original_sku_price,
            count_of_reviews, star_rating, count_of_star_ratings,
            detailed_review_content, trade_in, sku_status,
            number_of_units_purchased_past_month, available_quantity_for_purchase, delivery_availability,
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
        values = [item] + list(row[4:])
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


def get_format_stats(cursor, target_date):
    """형식 검증 통계 — 대시보드용"""

    total_format_issues = 0
    format_validation = {
        'type': 'format',
        'type_name': '형식 검증',
        'type_name_en': 'Format Validation',
        'description': '데이터 형식 및 패턴 검증',
        'icon': '📋',
        'tables': []
    }

    # tv_item_mst에서 유효한 item 목록 조회
    cursor.execute("SELECT DISTINCT item FROM tv_item_mst")
    tv_valid_items = set(row[0] for row in cursor.fetchall())

    # TV Retail 형식 검증 - 청크 단위 전수검사
    tv_format_errors = []
    tv_format_by_retailer = {'Amazon': 0, 'Bestbuy': 0, 'Walmart': 0}
    tv_format_total_by_retailer = {'Amazon': 0, 'Bestbuy': 0, 'Walmart': 0}
    tv_format_rows_count = 0

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

            if account_name in tv_format_total_by_retailer:
                tv_format_total_by_retailer[account_name] += 1
            else:
                tv_format_total_by_retailer[account_name] = 1

            values = list(row[2:])

            for field, value in zip(all_fields, values):
                error = validate_tv_field(field, value, account_name)
                if error:
                    errors.append({'field': field, 'value': str(value)[:30] if value else '', 'error': error})

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

    for product_line in ('ref', 'ldy'):
        sea_table_stats, sea_issue_total = _get_sea_retail_format_stats_table(cursor, target_date, product_line)
        format_validation['tables'].append(sea_table_stats)
        total_format_issues += sea_issue_total

    # hhp_item_mst
    hhp_valid_items = set()

    # HHP Retail - 청크 단위 전수검사
    hhp_format_errors = []
    hhp_format_by_retailer = {'Amazon': 0, 'Bestbuy': 0, 'Walmart': 0}
    hhp_format_total_by_retailer = {'Amazon': 0, 'Bestbuy': 0, 'Walmart': 0}
    hhp_format_rows_count = 0

    hhp_fields = [
        'item', 'page_type', 'product_url', 'main_rank', 'bsr_rank', 'trend_rank',
        'final_sku_price', 'original_sku_price',
        'count_of_reviews', 'star_rating', 'count_of_star_ratings',
        'detailed_review_content', 'trade_in', 'sku_status',
        'number_of_units_purchased_past_month', 'available_quantity_for_purchase', 'delivery_availability',
        'sku_popularity', 'retailer_membership_discounts',
        'rank_1', 'rank_2', 'summarized_review_content',
        'savings', 'offer', 'retailer_sku_name_similar', 'recommendation_intent',
        'number_of_ppl_purchased_yesterday', 'number_of_ppl_added_to_carts', 'discount_type'
    ]

    hhp_offset = 0
    while False:
        cursor.execute("""
            SELECT
                account_name, id, item, page_type, product_url,
                main_rank, bsr_rank, trend_rank, final_sku_price, original_sku_price,
                count_of_reviews, star_rating, count_of_star_ratings,
                detailed_review_content, trade_in, sku_status,
                number_of_units_purchased_past_month, available_quantity_for_purchase, delivery_availability,
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

            if account_name in hhp_format_total_by_retailer:
                hhp_format_total_by_retailer[account_name] += 1
            else:
                hhp_format_total_by_retailer[account_name] = 1

            values = list(row[2:])

            for field, value in zip(hhp_fields, values):
                error = validate_hhp_field(field, value, account_name)
                if error:
                    errors.append({'field': field, 'value': str(value)[:30] if value else '', 'error': error})

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
    format_validation['tables'] = [t for t in format_validation['tables'] if t.get('table') != 'hhp_retail']
    total_format_issues -= hhp_format_issue_total

    # YouTube 형식 검증
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

    # Market 형식 검증
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

    return format_validation, total_format_issues
