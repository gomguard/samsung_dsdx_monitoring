"""
Layer 4 API: 문맥/의미 기반 검증 (Contextual & Semantic Validation)
- LLM 기반 감성분석 결과 검증
- 리뷰/댓글 문맥 분석
- 의미적 일관성 체크
"""

from django.http import JsonResponse
from datetime import datetime, timedelta
from apps.common.db import get_dx_connection


def layer_stats(request):
    """Layer 4 통계 API - 문맥/의미 검증"""
    date_str = request.GET.get('date')
    product_line = request.GET.get('type', 'all')

    if date_str:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    else:
        target_date = (datetime.now() - timedelta(days=1)).date()

    results = {
        'timestamp': datetime.now().isoformat(),
        'date': str(target_date),
        'layer': 4,
        'name': '문맥/의미 검증',
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

    try:
        conn = get_dx_connection()
        cursor = conn.cursor()

        total_checked = 0
        total_failed = 0

        # ============================================================
        # 1. TV 감성분석 완료 여부 검증
        # ============================================================
        if product_line in ['tv', 'all']:
            cursor.execute("""
                SELECT
                    COUNT(*) as total,
                    COUNT(CASE WHEN sentiment_score IS NOT NULL THEN 1 END) as analyzed,
                    COUNT(CASE WHEN sentiment_score IS NOT NULL AND sentiment_score BETWEEN -1 AND 1 THEN 1 END) as valid_range
                FROM tv_retail_com
                WHERE DATE(crawl_datetime::timestamp) = %s
            """, (target_date,))

            tv_result = cursor.fetchone()
            tv_total = tv_result[0] or 0
            tv_analyzed = tv_result[1] or 0
            tv_valid_range = tv_result[2] or 0

            total_checked += tv_total
            not_analyzed = tv_total - tv_analyzed
            total_failed += not_analyzed

            results['checks'].append({
                'name': 'TV 감성분석 완료',
                'description': 'sentiment_score 분석 완료율',
                'checked': tv_total,
                'passed': tv_analyzed,
                'failed': not_analyzed,
                'analysis_rate': round((tv_analyzed / tv_total * 100), 1) if tv_total > 0 else 0,
                'status': 'OK' if tv_analyzed >= tv_total * 0.9 else ('WARNING' if tv_analyzed >= tv_total * 0.7 else 'CRITICAL')
            })

            # 감성점수 범위 검증 (-1 ~ 1)
            invalid_range = tv_analyzed - tv_valid_range
            results['checks'].append({
                'name': 'TV 감성점수 범위',
                'description': '감성점수가 -1 ~ 1 범위 내인지 검증',
                'checked': tv_analyzed,
                'passed': tv_valid_range,
                'failed': invalid_range,
                'status': 'OK' if invalid_range == 0 else 'CRITICAL'
            })
            total_failed += invalid_range

        # ============================================================
        # 2. HHP 감성분석 완료 여부 검증
        # ============================================================
        if product_line in ['hhp', 'all']:
            cursor.execute("""
                SELECT
                    COUNT(*) as total,
                    COUNT(CASE WHEN sentiment_score IS NOT NULL THEN 1 END) as analyzed,
                    COUNT(CASE WHEN sentiment_score IS NOT NULL AND sentiment_score BETWEEN -1 AND 1 THEN 1 END) as valid_range
                FROM hhp_retail_com
                WHERE DATE(crawl_strdatetime::timestamp) = %s
            """, (target_date,))

            hhp_result = cursor.fetchone()
            hhp_total = hhp_result[0] or 0
            hhp_analyzed = hhp_result[1] or 0
            hhp_valid_range = hhp_result[2] or 0

            total_checked += hhp_total
            hhp_not_analyzed = hhp_total - hhp_analyzed
            total_failed += hhp_not_analyzed

            results['checks'].append({
                'name': 'HHP 감성분석 완료',
                'description': 'sentiment_score 분석 완료율',
                'checked': hhp_total,
                'passed': hhp_analyzed,
                'failed': hhp_not_analyzed,
                'analysis_rate': round((hhp_analyzed / hhp_total * 100), 1) if hhp_total > 0 else 0,
                'status': 'OK' if hhp_analyzed >= hhp_total * 0.9 else 'WARNING'
            })

        # ============================================================
        # 3. YouTube 댓글 감성분석 검증
        # ============================================================
        if product_line == 'all':
            cursor.execute("""
                SELECT
                    COUNT(*) as total,
                    COUNT(CASE WHEN sentiment IS NOT NULL THEN 1 END) as analyzed
                FROM youtube_comments
                WHERE DATE(crawled_at) = %s
            """, (target_date,))

            yt_result = cursor.fetchone()
            yt_total = yt_result[0] or 0
            yt_analyzed = yt_result[1] or 0

            total_checked += yt_total
            yt_not_analyzed = yt_total - yt_analyzed
            total_failed += yt_not_analyzed

            results['checks'].append({
                'name': 'YouTube 댓글 감성분석',
                'description': '댓글 감성분석 완료율',
                'checked': yt_total,
                'passed': yt_analyzed,
                'failed': yt_not_analyzed,
                'analysis_rate': round((yt_analyzed / yt_total * 100), 1) if yt_total > 0 else 0,
                'status': 'OK' if yt_analyzed >= yt_total * 0.8 else 'WARNING'
            })

        # ============================================================
        # 4. LLM 수요 예측 검증
        # ============================================================
        if product_line == 'all':
            cursor.execute("""
                SELECT
                    COUNT(*) as total,
                    COUNT(CASE WHEN forecast_value IS NOT NULL THEN 1 END) as valid
                FROM openai_forecast_results
                WHERE DATE(created_at) = %s
            """, (target_date,))

            forecast_result = cursor.fetchone()
            forecast_total = forecast_result[0] or 0
            forecast_valid = forecast_result[1] or 0

            if forecast_total > 0:
                total_checked += forecast_total
                forecast_invalid = forecast_total - forecast_valid
                total_failed += forecast_invalid

                results['checks'].append({
                    'name': 'LLM 수요 예측',
                    'description': 'OpenAI 기반 수요 예측 결과 검증',
                    'checked': forecast_total,
                    'passed': forecast_valid,
                    'failed': forecast_invalid,
                    'status': 'OK' if forecast_valid == forecast_total else 'WARNING'
                })

        cursor.close()
        conn.close()

        # Summary 계산
        total_passed = total_checked - total_failed
        results['summary'] = {
            'total_checked': total_checked,
            'passed': total_passed,
            'failed': total_failed,
            'pass_rate': round((total_passed / total_checked * 100), 2) if total_checked > 0 else 0,
            'status': 'OK' if total_failed < total_checked * 0.1 else ('WARNING' if total_failed < total_checked * 0.2 else 'CRITICAL')
        }

    except Exception as e:
        results['error'] = str(e)
        results['summary']['status'] = 'ERROR'

    return JsonResponse(results)


def sentiment_distribution(request):
    """감성분석 분포 조회 API"""
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
                    CASE
                        WHEN sentiment_score > 0.3 THEN 'Positive'
                        WHEN sentiment_score < -0.3 THEN 'Negative'
                        ELSE 'Neutral'
                    END as sentiment_category,
                    COUNT(*) as count,
                    ROUND(AVG(sentiment_score)::numeric, 3) as avg_score
                FROM tv_retail_com
                WHERE DATE(crawl_datetime::timestamp) = %s
                AND sentiment_score IS NOT NULL
                GROUP BY sentiment_category
                ORDER BY count DESC
            """, (target_date,))
        else:
            cursor.execute("""
                SELECT
                    CASE
                        WHEN sentiment_score > 0.3 THEN 'Positive'
                        WHEN sentiment_score < -0.3 THEN 'Negative'
                        ELSE 'Neutral'
                    END as sentiment_category,
                    COUNT(*) as count,
                    ROUND(AVG(sentiment_score)::numeric, 3) as avg_score
                FROM hhp_retail_com
                WHERE DATE(crawl_strdatetime::timestamp) = %s
                AND sentiment_score IS NOT NULL
                GROUP BY sentiment_category
                ORDER BY count DESC
            """, (target_date,))

        rows = cursor.fetchall()
        distribution = []
        total = sum(row[1] for row in rows)

        for row in rows:
            distribution.append({
                'category': row[0],
                'count': row[1],
                'percentage': round((row[1] / total * 100), 1) if total > 0 else 0,
                'avg_score': float(row[2]) if row[2] else None
            })

        cursor.close()
        conn.close()

        return JsonResponse({
            'date': str(target_date),
            'product_line': product_line.upper(),
            'total_analyzed': total,
            'distribution': distribution
        })

    except Exception as e:
        return JsonResponse({'error': str(e)})


def unanalyzed_items(request):
    """감성분석 미완료 항목 조회 API"""
    date_str = request.GET.get('date')
    product_line = request.GET.get('type', 'tv')
    limit = int(request.GET.get('limit', 50))

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
                    crawl_datetime
                FROM tv_retail_com
                WHERE DATE(crawl_datetime::timestamp) = %s
                AND sentiment_score IS NULL
                ORDER BY crawl_datetime DESC
                LIMIT %s
            """, (target_date, limit))
        else:
            cursor.execute("""
                SELECT
                    product_name,
                    account_name,
                    price,
                    crawl_strdatetime
                FROM hhp_retail_com
                WHERE DATE(crawl_strdatetime::timestamp) = %s
                AND sentiment_score IS NULL
                ORDER BY crawl_strdatetime DESC
                LIMIT %s
            """, (target_date, limit))

        rows = cursor.fetchall()
        items = []
        for row in rows:
            items.append({
                'product_name': row[0],
                'retailer': row[1],
                'price': float(row[2]) if row[2] else None,
                'timestamp': str(row[3]) if row[3] else None
            })

        cursor.close()
        conn.close()

        return JsonResponse({
            'date': str(target_date),
            'product_line': product_line.upper(),
            'total_unanalyzed': len(items),
            'items': items
        })

    except Exception as e:
        return JsonResponse({'error': str(e)})


def retailer_sentiment(request):
    """리테일러별 감성분석 현황 API"""
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
                    account_name,
                    COUNT(*) as total,
                    COUNT(CASE WHEN sentiment_score IS NOT NULL THEN 1 END) as analyzed,
                    ROUND(AVG(sentiment_score)::numeric, 3) as avg_score,
                    COUNT(CASE WHEN sentiment_score > 0.3 THEN 1 END) as positive,
                    COUNT(CASE WHEN sentiment_score < -0.3 THEN 1 END) as negative
                FROM tv_retail_com
                WHERE DATE(crawl_datetime::timestamp) = %s
                GROUP BY account_name
                ORDER BY total DESC
            """, (target_date,))
        else:
            cursor.execute("""
                SELECT
                    account_name,
                    COUNT(*) as total,
                    COUNT(CASE WHEN sentiment_score IS NOT NULL THEN 1 END) as analyzed,
                    ROUND(AVG(sentiment_score)::numeric, 3) as avg_score,
                    COUNT(CASE WHEN sentiment_score > 0.3 THEN 1 END) as positive,
                    COUNT(CASE WHEN sentiment_score < -0.3 THEN 1 END) as negative
                FROM hhp_retail_com
                WHERE DATE(crawl_strdatetime::timestamp) = %s
                GROUP BY account_name
                ORDER BY total DESC
            """, (target_date,))

        rows = cursor.fetchall()
        retailers = []
        for row in rows:
            retailers.append({
                'retailer': row[0],
                'total': row[1],
                'analyzed': row[2],
                'analysis_rate': round((row[2] / row[1] * 100), 1) if row[1] > 0 else 0,
                'avg_score': float(row[3]) if row[3] else None,
                'positive_count': row[4],
                'negative_count': row[5]
            })

        cursor.close()
        conn.close()

        return JsonResponse({
            'date': str(target_date),
            'product_line': product_line.upper(),
            'retailers': retailers
        })

    except Exception as e:
        return JsonResponse({'error': str(e)})
