"""
시계열 이상치 API — 가격/순위 변동, 중복, 리뷰 수 급변 상세
"""

from datetime import datetime, timedelta
from django.http import JsonResponse
from apps.common.db import get_dx_connection
from apps.common.response import safe_error, log_error


def time_series_detail(request):
    """시계열 이상치 상세 API"""
    date_str = request.GET.get('date')
    product_line = request.GET.get('type', 'tv')
    check_type = request.GET.get('check', 'price')
    period = request.GET.get('period', 'daily')

    if date_str:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    else:
        target_date = (datetime.now() - timedelta(days=1)).date()

    if period == 'weekly':
        compare_date = target_date - timedelta(days=7)
        threshold = 0.5
    else:
        compare_date = target_date - timedelta(days=1)
        threshold = 0.5

    try:
        conn = get_dx_connection()
        cursor = conn.cursor()

        if product_line == 'tv':
            if check_type == 'price':
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
                        AND final_sku_price !~ '[a-zA-Z]'
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
                        AND final_sku_price !~ '[a-zA-Z]'
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
                        AND final_sku_price !~ '[a-zA-Z]'
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
                    'period': row[8] if len(row) > 8 else None
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
                    'period': row[8] if len(row) > 8 else None
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
