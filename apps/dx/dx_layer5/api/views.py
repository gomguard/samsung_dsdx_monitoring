"""
Layer 5 API: 전문가 전수 검수 (Expert Review & Final Validation)
- 자동 검증 실패 항목 수동 검토
- 전문가 승인/거부 처리
- 최종 품질 인증
"""

from django.http import JsonResponse
from datetime import datetime, timedelta
from apps.common.db import get_dx_connection
from apps.common.response import safe_error, log_error


def layer_stats(request):
    """Layer 5 통계 API - 전문가 검수 현황"""
    date_str = request.GET.get('date')

    if date_str:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    else:
        target_date = (datetime.now() - timedelta(days=1)).date()

    results = {
        'timestamp': datetime.now().isoformat(),
        'date': str(target_date),
        'layer': 5,
        'name': '전문가 전수 검수',
        'review_queue': [],
        'summary': {
            'pending_review': 0,
            'approved': 0,
            'rejected': 0,
            'auto_passed': 0,
            'total_processed': 0,
            'status': 'OK'
        }
    }

    try:
        conn = get_dx_connection()
        cursor = conn.cursor()

        # ============================================================
        # 1. TV 검토 대기 항목 (이상치 + 미분석)
        # ============================================================

        # TV 가격 이상치
        cursor.execute("""
            SELECT COUNT(*) FROM tv_retail_com
            WHERE DATE(crawl_datetime::timestamp) = %s
            AND (price < 0 OR price > 50000)
        """, (target_date,))
        tv_price_issues = cursor.fetchone()[0] or 0

        # TV 감성분석 미완료
        cursor.execute("""
            SELECT COUNT(*) FROM tv_retail_com
            WHERE DATE(crawl_datetime::timestamp) = %s
            AND sentiment_score IS NULL
        """, (target_date,))
        tv_unanalyzed = cursor.fetchone()[0] or 0

        # TV 전체 수집량
        cursor.execute("""
            SELECT COUNT(*) FROM tv_retail_com
            WHERE DATE(crawl_datetime::timestamp) = %s
        """, (target_date,))
        tv_total = cursor.fetchone()[0] or 0

        tv_pending = tv_price_issues + tv_unanalyzed
        tv_auto_passed = tv_total - tv_pending

        results['review_queue'].append({
            'category': 'TV Retail',
            'total': tv_total,
            'pending': tv_pending,
            'price_issues': tv_price_issues,
            'unanalyzed': tv_unanalyzed,
            'auto_passed': tv_auto_passed,
            'pass_rate': round((tv_auto_passed / tv_total * 100), 1) if tv_total > 0 else 0
        })

        # ============================================================
        # 2. HHP 검토 대기 항목
        # ============================================================

        cursor.execute("""
            SELECT COUNT(*) FROM hhp_retail_com
            WHERE DATE(crawl_strdatetime::timestamp) = %s
            AND (price < 0 OR price > 5000)
        """, (target_date,))
        hhp_price_issues = cursor.fetchone()[0] or 0

        cursor.execute("""
            SELECT COUNT(*) FROM hhp_retail_com
            WHERE DATE(crawl_strdatetime::timestamp) = %s
            AND sentiment_score IS NULL
        """, (target_date,))
        hhp_unanalyzed = cursor.fetchone()[0] or 0

        cursor.execute("""
            SELECT COUNT(*) FROM hhp_retail_com
            WHERE DATE(crawl_strdatetime::timestamp) = %s
        """, (target_date,))
        hhp_total = cursor.fetchone()[0] or 0

        hhp_pending = hhp_price_issues + hhp_unanalyzed
        hhp_auto_passed = hhp_total - hhp_pending

        results['review_queue'].append({
            'category': 'HHP Retail',
            'total': hhp_total,
            'pending': hhp_pending,
            'price_issues': hhp_price_issues,
            'unanalyzed': hhp_unanalyzed,
            'auto_passed': hhp_auto_passed,
            'pass_rate': round((hhp_auto_passed / hhp_total * 100), 1) if hhp_total > 0 else 0
        })

        # ============================================================
        # 3. YouTube 검토 대기 항목
        # ============================================================

        cursor.execute("""
            SELECT COUNT(*) FROM youtube_videos
            WHERE DATE(crawled_at) = %s
        """, (target_date,))
        yt_total = cursor.fetchone()[0] or 0

        cursor.execute("""
            SELECT COUNT(*) FROM youtube_comments
            WHERE DATE(crawled_at) = %s
            AND sentiment IS NULL
        """, (target_date,))
        yt_unanalyzed = cursor.fetchone()[0] or 0

        results['review_queue'].append({
            'category': 'YouTube',
            'total': yt_total,
            'pending': yt_unanalyzed,
            'auto_passed': yt_total - yt_unanalyzed if yt_total > yt_unanalyzed else 0,
            'pass_rate': round(((yt_total - yt_unanalyzed) / yt_total * 100), 1) if yt_total > 0 else 0
        })

        # ============================================================
        # 4. Market Trend 검토 대기 항목
        # ============================================================

        cursor.execute("""
            SELECT COUNT(*) FROM market_trend
            WHERE DATE(crawled_at) = %s
        """, (target_date,))
        trend_total = cursor.fetchone()[0] or 0

        results['review_queue'].append({
            'category': 'Market Trend',
            'total': trend_total,
            'pending': 0,  # 트렌드 데이터는 자동 통과
            'auto_passed': trend_total,
            'pass_rate': 100.0 if trend_total > 0 else 0
        })

        cursor.close()
        conn.close()

        # Summary 계산
        total_pending = sum(q.get('pending', 0) for q in results['review_queue'])
        total_auto_passed = sum(q.get('auto_passed', 0) for q in results['review_queue'])
        total_all = sum(q.get('total', 0) for q in results['review_queue'])

        results['summary'] = {
            'pending_review': total_pending,
            'approved': 0,  # TODO: 승인 테이블 연동
            'rejected': 0,  # TODO: 거부 테이블 연동
            'auto_passed': total_auto_passed,
            'total_processed': total_all,
            'pass_rate': round((total_auto_passed / total_all * 100), 1) if total_all > 0 else 0,
            'status': 'OK' if total_pending == 0 else ('PENDING' if total_pending < total_all * 0.1 else 'CRITICAL')
        }

    except Exception as e:
        results['error'] = log_error(e)
        results['summary']['status'] = 'ERROR'

    return JsonResponse(results)


def pending_items(request):
    """검토 대기 항목 상세 조회 API"""
    date_str = request.GET.get('date')
    category = request.GET.get('category', 'tv')  # tv, hhp, youtube
    issue_type = request.GET.get('issue', 'all')  # all, price, unanalyzed
    try:
        limit = min(int(request.GET.get('limit', 50)), 500)
    except (ValueError, TypeError):
        limit = 50

    if date_str:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    else:
        target_date = (datetime.now() - timedelta(days=1)).date()

    try:
        conn = get_dx_connection()
        cursor = conn.cursor()

        if category == 'tv':
            if issue_type == 'price':
                cursor.execute("""
                    SELECT product_name, account_name, price, main_rank, crawl_datetime
                    FROM tv_retail_com
                    WHERE DATE(crawl_datetime::timestamp) = %s
                    AND (price < 0 OR price > 50000)
                    ORDER BY ABS(price) DESC
                    LIMIT %s
                """, (target_date, limit))
            elif issue_type == 'unanalyzed':
                cursor.execute("""
                    SELECT product_name, account_name, price, main_rank, crawl_datetime
                    FROM tv_retail_com
                    WHERE DATE(crawl_datetime::timestamp) = %s
                    AND sentiment_score IS NULL
                    ORDER BY crawl_datetime DESC
                    LIMIT %s
                """, (target_date, limit))
            else:
                cursor.execute("""
                    SELECT product_name, account_name, price, main_rank, crawl_datetime
                    FROM tv_retail_com
                    WHERE DATE(crawl_datetime::timestamp) = %s
                    AND (price < 0 OR price > 50000 OR sentiment_score IS NULL)
                    ORDER BY crawl_datetime DESC
                    LIMIT %s
                """, (target_date, limit))
        elif category == 'hhp':
            cursor.execute("""
                SELECT product_name, account_name, price, main_rank, crawl_strdatetime
                FROM hhp_retail_com
                WHERE DATE(crawl_strdatetime::timestamp) = %s
                AND (price < 0 OR price > 5000 OR sentiment_score IS NULL)
                ORDER BY crawl_strdatetime DESC
                LIMIT %s
            """, (target_date, limit))
        else:
            cursor.execute("""
                SELECT title, channel_name, view_count, comment_count, crawled_at
                FROM youtube_videos
                WHERE DATE(crawled_at) = %s
                ORDER BY crawled_at DESC
                LIMIT %s
            """, (target_date, limit))

        rows = cursor.fetchall()
        items = []

        if category in ['tv', 'hhp']:
            for row in rows:
                items.append({
                    'product_name': row[0],
                    'retailer': row[1],
                    'price': float(row[2]) if row[2] else None,
                    'rank': row[3],
                    'timestamp': str(row[4]) if row[4] else None,
                    'issue_type': 'price' if row[2] and (row[2] < 0 or row[2] > 50000) else 'unanalyzed'
                })
        else:
            for row in rows:
                items.append({
                    'title': row[0],
                    'channel': row[1],
                    'view_count': row[2],
                    'comment_count': row[3],
                    'timestamp': str(row[4]) if row[4] else None
                })

        cursor.close()
        conn.close()

        return JsonResponse({
            'date': str(target_date),
            'category': category.upper(),
            'issue_type': issue_type,
            'total_items': len(items),
            'items': items
        })

    except Exception as e:
        return safe_error(e)


def quality_summary(request):
    """데이터 품질 요약 API - 5단계 방어 체계 전체 현황"""
    date_str = request.GET.get('date')

    if date_str:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    else:
        target_date = (datetime.now() - timedelta(days=1)).date()

    try:
        conn = get_dx_connection()
        cursor = conn.cursor()

        # TV 전체 현황
        cursor.execute("""
            SELECT
                COUNT(*) as total,
                COUNT(CASE WHEN product_name IS NOT NULL AND product_name != '' THEN 1 END) as valid_name,
                COUNT(CASE WHEN price IS NOT NULL AND price >= 0 AND price <= 50000 THEN 1 END) as valid_price,
                COUNT(CASE WHEN sentiment_score IS NOT NULL THEN 1 END) as analyzed
            FROM tv_retail_com
            WHERE DATE(crawl_datetime::timestamp) = %s
        """, (target_date,))
        tv_result = cursor.fetchone()

        # HHP 전체 현황
        cursor.execute("""
            SELECT
                COUNT(*) as total,
                COUNT(CASE WHEN product_name IS NOT NULL AND product_name != '' THEN 1 END) as valid_name,
                COUNT(CASE WHEN price IS NOT NULL AND price >= 0 AND price <= 5000 THEN 1 END) as valid_price,
                COUNT(CASE WHEN sentiment_score IS NOT NULL THEN 1 END) as analyzed
            FROM hhp_retail_com
            WHERE DATE(crawl_strdatetime::timestamp) = %s
        """, (target_date,))
        hhp_result = cursor.fetchone()

        cursor.close()
        conn.close()

        # 통과율 계산
        tv_total = tv_result[0] or 0
        tv_layer1_pass = tv_total  # 수집 완료 = Layer 1 통과
        tv_layer2_pass = min(tv_result[1] or 0, tv_result[2] or 0)  # 필수값 검증
        tv_layer3_pass = tv_result[2] or 0  # 가격 이상치 없음
        tv_layer4_pass = tv_result[3] or 0  # 감성분석 완료
        tv_layer5_pass = min(tv_layer3_pass, tv_layer4_pass)  # 최종 통과

        hhp_total = hhp_result[0] or 0
        hhp_layer5_pass = min(hhp_result[2] or 0, hhp_result[3] or 0)

        total_raw = tv_total + hhp_total
        total_trusted = tv_layer5_pass + hhp_layer5_pass

        return JsonResponse({
            'date': str(target_date),
            'quality_metrics': {
                'tv': {
                    'total': tv_total,
                    'layer1_pass': tv_layer1_pass,
                    'layer2_pass': tv_layer2_pass,
                    'layer3_pass': tv_layer3_pass,
                    'layer4_pass': tv_layer4_pass,
                    'layer5_pass': tv_layer5_pass,
                    'final_pass_rate': round((tv_layer5_pass / tv_total * 100), 1) if tv_total > 0 else 0
                },
                'hhp': {
                    'total': hhp_total,
                    'layer5_pass': hhp_layer5_pass,
                    'final_pass_rate': round((hhp_layer5_pass / hhp_total * 100), 1) if hhp_total > 0 else 0
                }
            },
            'summary': {
                'total_raw_data': total_raw,
                'total_trusted_data': total_trusted,
                'overall_trust_rate': round((total_trusted / total_raw * 100), 1) if total_raw > 0 else 0,
                'status': 'TRUSTED' if total_trusted >= total_raw * 0.9 else ('REVIEW_NEEDED' if total_trusted >= total_raw * 0.7 else 'CRITICAL')
            }
        })

    except Exception as e:
        return safe_error(e)
