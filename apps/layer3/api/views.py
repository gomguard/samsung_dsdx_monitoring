"""
Layer 3 API: 이상치/특수 케이스 검수 (Outlier Detection & Special Cases)
- 통계적 이상치 탐지 (가격, 순위, 수량 등)
- 급격한 변화 패턴 감지
- 특수 케이스 분류
"""

from django.http import JsonResponse
from datetime import datetime, timedelta
from apps.common.db import get_dx_connection


def layer_stats(request):
    """Layer 3 통계 API - 이상치 탐지"""
    date_str = request.GET.get('date')
    product_line = request.GET.get('type', 'all')

    if date_str:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    else:
        target_date = (datetime.now() - timedelta(days=1)).date()

    prev_date = target_date - timedelta(days=1)

    results = {
        'timestamp': datetime.now().isoformat(),
        'date': str(target_date),
        'layer': 3,
        'name': '이상치/특수 케이스 검수',
        'product_line': product_line.upper(),
        'checks': [],
        'anomalies': [],
        'summary': {
            'total_checked': 0,
            'passed': 0,
            'failed': 0,
            'pass_rate': 0,
            'status': 'OK'
        }
    }

    try:
        conn = get_dx_connection()
        cursor = conn.cursor()

        total_checked = 0
        total_anomalies = 0

        # ============================================================
        # 1. TV 가격 이상치 탐지
        # ============================================================
        if product_line in ['tv', 'all']:
            # 음수 또는 비정상적인 가격
            cursor.execute("""
                SELECT COUNT(*) FROM tv_retail_com
                WHERE DATE(crawl_datetime::timestamp) = %s
                AND (final_sku_price < 0 OR final_sku_price > 50000)
            """, (target_date,))
            tv_price_anomaly = cursor.fetchone()[0] or 0

            cursor.execute("""
                SELECT COUNT(*) FROM tv_retail_com
                WHERE DATE(crawl_datetime::timestamp) = %s
            """, (target_date,))
            tv_total = cursor.fetchone()[0] or 0

            total_checked += tv_total
            total_anomalies += tv_price_anomaly

            results['checks'].append({
                'name': 'TV 가격 범위',
                'description': '가격이 0 ~ 50,000 범위 내인지 검증',
                'checked': tv_total,
                'passed': tv_total - tv_price_anomaly,
                'failed': tv_price_anomaly,
                'threshold': {'min': 0, 'max': 50000},
                'status': 'OK' if tv_price_anomaly == 0 else ('WARNING' if tv_price_anomaly < tv_total * 0.01 else 'CRITICAL')
            })

            # 순위 이상치 (1000위 초과)
            cursor.execute("""
                SELECT COUNT(*) FROM tv_retail_com
                WHERE DATE(crawl_datetime::timestamp) = %s
                AND main_rank IS NOT NULL
                AND main_rank > 500
            """, (target_date,))
            tv_rank_anomaly = cursor.fetchone()[0] or 0
            total_anomalies += tv_rank_anomaly

            results['checks'].append({
                'name': 'TV 순위 범위',
                'description': '메인 순위가 500위 이내인지 검증',
                'checked': tv_total,
                'passed': tv_total - tv_rank_anomaly,
                'failed': tv_rank_anomaly,
                'threshold': {'max': 500},
                'status': 'OK' if tv_rank_anomaly < tv_total * 0.1 else 'WARNING'
            })

            # 급격한 가격 변동 탐지 (전일 대비 30% 이상)
            cursor.execute("""
                WITH today AS (
                    SELECT item, account_name, final_sku_price as price
                    FROM tv_retail_com
                    WHERE DATE(crawl_datetime::timestamp) = %s
                    AND final_sku_price IS NOT NULL
                ),
                yesterday AS (
                    SELECT item, account_name, final_sku_price as price
                    FROM tv_retail_com
                    WHERE DATE(crawl_datetime::timestamp) = %s
                    AND final_sku_price IS NOT NULL
                )
                SELECT COUNT(*) FROM today t
                JOIN yesterday y ON t.item = y.item AND t.account_name = y.account_name
                WHERE ABS(t.price - y.price) / NULLIF(y.price, 0) > 0.3
            """, (target_date, prev_date))
            tv_price_change = cursor.fetchone()[0] or 0
            total_anomalies += tv_price_change

            results['checks'].append({
                'name': 'TV 가격 급변',
                'description': '전일 대비 30% 이상 가격 변동',
                'checked': tv_total,
                'passed': tv_total - tv_price_change,
                'failed': tv_price_change,
                'threshold': {'change_rate': 0.3},
                'status': 'OK' if tv_price_change < 10 else ('WARNING' if tv_price_change < 50 else 'CRITICAL')
            })

        # ============================================================
        # 2. HHP 가격 이상치 탐지
        # ============================================================
        if product_line in ['hhp', 'all']:
            cursor.execute("""
                SELECT COUNT(*) FROM hhp_retail_com
                WHERE DATE(crawl_strdatetime::timestamp) = %s
                AND (final_sku_price < 0 OR final_sku_price > 5000)
            """, (target_date,))
            hhp_price_anomaly = cursor.fetchone()[0] or 0

            cursor.execute("""
                SELECT COUNT(*) FROM hhp_retail_com
                WHERE DATE(crawl_strdatetime::timestamp) = %s
            """, (target_date,))
            hhp_total = cursor.fetchone()[0] or 0

            total_checked += hhp_total
            total_anomalies += hhp_price_anomaly

            results['checks'].append({
                'name': 'HHP 가격 범위',
                'description': '가격이 0 ~ 5,000 범위 내인지 검증',
                'checked': hhp_total,
                'passed': hhp_total - hhp_price_anomaly,
                'failed': hhp_price_anomaly,
                'threshold': {'min': 0, 'max': 5000},
                'status': 'OK' if hhp_price_anomaly == 0 else 'WARNING'
            })

            # HHP 순위 이상치
            cursor.execute("""
                SELECT COUNT(*) FROM hhp_retail_com
                WHERE DATE(crawl_strdatetime::timestamp) = %s
                AND main_rank IS NOT NULL
                AND main_rank > 300
            """, (target_date,))
            hhp_rank_anomaly = cursor.fetchone()[0] or 0
            total_anomalies += hhp_rank_anomaly

            results['checks'].append({
                'name': 'HHP 순위 범위',
                'description': '메인 순위가 300위 이내인지 검증',
                'checked': hhp_total,
                'passed': hhp_total - hhp_rank_anomaly,
                'failed': hhp_rank_anomaly,
                'threshold': {'max': 300},
                'status': 'OK' if hhp_rank_anomaly < hhp_total * 0.1 else 'WARNING'
            })

        # ============================================================
        # 3. YouTube 조회수 이상치
        # ============================================================
        if product_line == 'all':
            cursor.execute("""
                SELECT COUNT(*) FROM youtube_videos
                WHERE DATE(created_at) = %s
                AND view_count IS NOT NULL
                AND view_count < 0
            """, (target_date,))
            yt_view_anomaly = cursor.fetchone()[0] or 0

            cursor.execute("""
                SELECT COUNT(*) FROM youtube_videos
                WHERE DATE(created_at) = %s
            """, (target_date,))
            yt_total = cursor.fetchone()[0] or 0

            total_checked += yt_total
            total_anomalies += yt_view_anomaly

            results['checks'].append({
                'name': 'YouTube 조회수',
                'description': '조회수가 음수가 아닌지 검증',
                'checked': yt_total,
                'passed': yt_total - yt_view_anomaly,
                'failed': yt_view_anomaly,
                'status': 'OK' if yt_view_anomaly == 0 else 'CRITICAL'
            })

        cursor.close()
        conn.close()

        # Summary 계산
        total_passed = total_checked - total_anomalies
        results['summary'] = {
            'total_checked': total_checked,
            'passed': total_passed,
            'failed': total_anomalies,
            'pass_rate': round((total_passed / total_checked * 100), 2) if total_checked > 0 else 0,
            'status': 'OK' if total_anomalies < total_checked * 0.02 else ('WARNING' if total_anomalies < total_checked * 0.05 else 'CRITICAL')
        }

    except Exception as e:
        results['error'] = str(e)
        results['summary']['status'] = 'ERROR'

    return JsonResponse(results)


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
                    price,
                    main_rank,
                    crawl_datetime
                FROM tv_retail_com
                WHERE DATE(crawl_datetime::timestamp) = %s
                AND (price < 0 OR price > 50000)
                ORDER BY price DESC
                LIMIT 50
            """, (target_date,))
        else:
            cursor.execute("""
                SELECT
                    product_name,
                    account_name,
                    price,
                    main_rank,
                    crawl_strdatetime
                FROM hhp_retail_com
                WHERE DATE(crawl_strdatetime::timestamp) = %s
                AND (price < 0 OR price > 5000)
                ORDER BY price DESC
                LIMIT 50
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
        return JsonResponse({'error': str(e)})


def price_changes(request):
    """급격한 가격 변동 조회 API"""
    date_str = request.GET.get('date')
    product_line = request.GET.get('type', 'tv')
    threshold = float(request.GET.get('threshold', 0.3))  # 기본 30%

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
                    SELECT product_name, account_name, price
                    FROM tv_retail_com
                    WHERE DATE(crawl_datetime::timestamp) = %s
                    AND price IS NOT NULL
                ),
                yesterday AS (
                    SELECT product_name, account_name, price
                    FROM tv_retail_com
                    WHERE DATE(crawl_datetime::timestamp) = %s
                    AND price IS NOT NULL
                )
                SELECT
                    t.product_name,
                    t.account_name,
                    y.price as prev_price,
                    t.price as curr_price,
                    ROUND(((t.price - y.price) / NULLIF(y.price, 0) * 100)::numeric, 2) as change_pct
                FROM today t
                JOIN yesterday y ON t.product_name = y.product_name AND t.account_name = y.account_name
                WHERE ABS(t.price - y.price) / NULLIF(y.price, 0) > %s
                ORDER BY ABS(t.price - y.price) / NULLIF(y.price, 0) DESC
                LIMIT 50
            """, (target_date, prev_date, threshold))
        else:
            cursor.execute("""
                WITH today AS (
                    SELECT product_name, account_name, price
                    FROM hhp_retail_com
                    WHERE DATE(crawl_strdatetime::timestamp) = %s
                    AND price IS NOT NULL
                ),
                yesterday AS (
                    SELECT product_name, account_name, price
                    FROM hhp_retail_com
                    WHERE DATE(crawl_strdatetime::timestamp) = %s
                    AND price IS NOT NULL
                )
                SELECT
                    t.product_name,
                    t.account_name,
                    y.price as prev_price,
                    t.price as curr_price,
                    ROUND(((t.price - y.price) / NULLIF(y.price, 0) * 100)::numeric, 2) as change_pct
                FROM today t
                JOIN yesterday y ON t.product_name = y.product_name AND t.account_name = y.account_name
                WHERE ABS(t.price - y.price) / NULLIF(y.price, 0) > %s
                ORDER BY ABS(t.price - y.price) / NULLIF(y.price, 0) DESC
                LIMIT 50
            """, (target_date, prev_date, threshold))

        rows = cursor.fetchall()
        changes = []
        for row in rows:
            changes.append({
                'product_name': row[0],
                'retailer': row[1],
                'prev_price': float(row[2]) if row[2] else None,
                'curr_price': float(row[3]) if row[3] else None,
                'change_pct': float(row[4]) if row[4] else None
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
        return JsonResponse({'error': str(e)})
