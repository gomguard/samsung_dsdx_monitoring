"""
시계열 이상치 API — 가격/순위 변동, 중복, 리뷰 수 급변 상세
"""

from datetime import datetime, timedelta
from django.http import JsonResponse
from apps.common.db import get_dx_connection, dx_table
from apps.common.response import safe_error, log_error
from apps.dx.dx_layer3.dashboard.services import validate_table_name as _validate_table_name


def time_series_detail(request):
    """시계열 이상치 상세 API — 이상치 item의 3일치 원본 데이터"""
    date_str = request.GET.get('date')
    detail_code = request.GET.get('detail_code', '')
    try:
        days = min(int(request.GET.get('days', 1)), 30)
    except (ValueError, TypeError):
        days = 1

    if not detail_code:
        return JsonResponse({'items': [], 'total': 0, 'anomaly_items': 0})

    if date_str:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    else:
        target_date = (datetime.now() - timedelta(days=1)).date()

    prev_date = target_date - timedelta(days=1)
    since_date = target_date - timedelta(days=days - 1)
    rules_table = dx_table('monitoring_timeseries_rules')

    conn = None
    try:
        conn = get_dx_connection()
        cursor = conn.cursor()

        # 규칙 조회
        cursor.execute(f"""
            SELECT table_name, date_column, query
            FROM {rules_table}
            WHERE detail_code = %s AND is_active = true
        """, [detail_code])
        rule = cursor.fetchone()
        if not rule:
            cursor.close()
            conn.close()
            return JsonResponse({'error': '규칙을 찾을 수 없습니다.'}, status=404)

        source_table, date_column, stored_query = rule
        _validate_table_name(source_table)

        if not stored_query:
            cursor.close()
            conn.close()
            return JsonResponse({'items': [], 'total': 0})

        # 1) 이상치 item 카운트 (오늘 기준)
        count_sql = f"SELECT COUNT(*) FROM ({stored_query}) x"
        cursor.execute(count_sql, (target_date, target_date, prev_date))
        anomaly_count = cursor.fetchone()[0] or 0

        # 2) 이상치 item의 원본 데이터 조회 (일수 범위)
        date_select = f'd.{date_column} AS crawl_datetime' if date_column != 'crawl_datetime' else 'd.crawl_datetime'

        if days == 1:
            date_filter = f"DATE(d.{date_column}::timestamp) = %s"
            date_params = [str(target_date)]
        else:
            date_filter = f"DATE(d.{date_column}::timestamp) >= %s AND DATE(d.{date_column}::timestamp) <= %s"
            date_params = [str(since_date), str(target_date)]

        combined_sql = f"""
            WITH _anomaly_items AS ({stored_query})
            SELECT d.id, d.item, d.account_name, d.final_sku_price, d.product_url, {date_select}, a.median_val
            FROM {source_table} d
            JOIN _anomaly_items a ON d.item = a.item
            WHERE {date_filter}
            ORDER BY d.item, d.account_name, d.{date_column} ASC
        """
        cursor.execute(combined_sql, (target_date, target_date, prev_date) + tuple(date_params))

        rows = []
        for row in cursor.fetchall():
            median = row[6]
            rows.append({
                'id': row[0],
                'item': row[1],
                'account_name': row[2],
                'final_sku_price': row[3] or '',
                'product_url': row[4] or '',
                'crawl_datetime': row[5].strftime('%Y-%m-%d %H:%M:%S') if hasattr(row[5], 'strftime') else str(row[5]) if row[5] else '',
                'median_price': f'${median:,.2f}' if median is not None else ''
            })

        cursor.close()
        conn.close()

        return JsonResponse({
            'date': str(target_date),
            'detail_code': detail_code,
            'total': len(rows),
            'anomaly_count': anomaly_count,
            'items': rows
        })

    except Exception as e:
        if conn:
            try:
                conn.close()
            except Exception:
                pass
        log_error(e)
        return safe_error(e, items=[])


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
                'period': row[7]
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
                    AND final_sku_price !~ '[a-zA-Z]'
                ),
                yesterday AS (
                    SELECT item, product_name, account_name,
                           CAST(REPLACE(REPLACE(SPLIT_PART(REPLACE(final_sku_price, '$', ''), '/', 1), ',', ''), ' ', '') AS NUMERIC) as price
                    FROM hhp_retail_com
                    WHERE DATE(crawl_strdatetime) = %s
                    AND final_sku_price IS NOT NULL
                    AND final_sku_price LIKE '$%%'
                    AND final_sku_price !~ '[a-zA-Z]'
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
