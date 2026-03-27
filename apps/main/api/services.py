"""
메인 대시보드 Services -- DB 조회 로직
"""

from datetime import datetime, timedelta
from apps.common.db import dx_connection, ds_connection


def get_dashboard_stats(target_date):
    """대시보드 전체 통계 조회

    Returns:
        dict with keys: layers, summary, collection_status
    """
    with dx_connection() as (conn, cursor):
        # ============================================================
        # Layer 1: 기본 통계 검수 - 수집량 확인
        # ============================================================
        layer1_checks = []

        # TV Retail 수집량
        cursor.execute("""
            SELECT COUNT(*) FROM tv_retail_com
            WHERE DATE(crawl_datetime::timestamp) = %s
        """, (target_date,))
        tv_count = cursor.fetchone()[0] or 0
        layer1_checks.append({'name': 'TV Retail', 'count': tv_count, 'expected': 300})

        # HHP Retail 수집량
        cursor.execute("""
            SELECT COUNT(*) FROM hhp_retail_com
            WHERE DATE(crawl_strdatetime::timestamp) = %s
        """, (target_date,))
        hhp_count = cursor.fetchone()[0] or 0
        layer1_checks.append({'name': 'HHP Retail', 'count': hhp_count, 'expected': 300})

        # Market Trend 수집량
        cursor.execute("""
            SELECT COUNT(*) FROM market_trend
            WHERE DATE(crawl_at_local_time) = %s
        """, (target_date,))
        trend_count = cursor.fetchone()[0] or 0
        layer1_checks.append({'name': 'Market Trend', 'count': trend_count, 'expected': 50})

        # YouTube 수집량
        cursor.execute("""
            SELECT COUNT(*) FROM youtube_videos
            WHERE DATE(created_at) = %s
        """, (target_date,))
        youtube_count = cursor.fetchone()[0] or 0
        layer1_checks.append({'name': 'YouTube', 'count': youtube_count, 'expected': 20})

        layer1_total = sum(c['count'] for c in layer1_checks)
        layer1_passed = sum(1 for c in layer1_checks if c['count'] >= c['expected'])
        layer1_failed = len(layer1_checks) - layer1_passed

        layer1 = {
            'name': '기본 통계 검수',
            'description': '수집 직후 행의 개수가 예상 범위 내에 있는지 확인',
            'total_checked': len(layer1_checks),
            'passed': layer1_passed,
            'failed': layer1_failed,
            'pass_rate': round((layer1_passed / len(layer1_checks) * 100), 1) if layer1_checks else 0,
            'total_records': layer1_total,
            'status': 'OK' if layer1_failed == 0 else ('WARNING' if layer1_failed <= 1 else 'CRITICAL'),
            'details': layer1_checks
        }

        # ============================================================
        # Layer 2: 형식/중복 검수
        # ============================================================
        cursor.execute("""
            SELECT
                COUNT(*) as total,
                COUNT(CASE WHEN retailer_sku_name IS NULL OR retailer_sku_name = '' THEN 1 END) as null_name,
                COUNT(CASE WHEN final_sku_price IS NULL THEN 1 END) as null_price
            FROM tv_retail_com
            WHERE DATE(crawl_datetime::timestamp) = %s
        """, (target_date,))
        tv_format = cursor.fetchone()

        cursor.execute("""
            SELECT COUNT(*) FROM (
                SELECT item, account_name, DATE(crawl_datetime::timestamp)
                FROM tv_retail_com
                WHERE DATE(crawl_datetime::timestamp) = %s
                GROUP BY item, account_name, DATE(crawl_datetime::timestamp)
                HAVING COUNT(*) > 1
            ) dup
        """, (target_date,))
        tv_duplicates = cursor.fetchone()[0] or 0

        layer2_total = tv_format[0] if tv_format else 0
        layer2_null_issues = (tv_format[1] or 0) + (tv_format[2] or 0) if tv_format else 0
        layer2_passed = layer2_total - layer2_null_issues - tv_duplicates

        layer2 = {
            'name': '형식/중복 검수',
            'description': '데이터 형식 검증 및 중복 데이터 탐지',
            'total_checked': layer2_total,
            'passed': max(0, layer2_passed),
            'failed': layer2_null_issues + tv_duplicates,
            'null_issues': layer2_null_issues,
            'duplicate_issues': tv_duplicates,
            'pass_rate': round((layer2_passed / layer2_total * 100), 1) if layer2_total > 0 else 0,
            'status': 'OK' if layer2_null_issues + tv_duplicates < layer2_total * 0.05 else 'WARNING'
        }

        # ============================================================
        # Layer 3: 이상치/특수 케이스
        # ============================================================
        price_anomalies = 0

        cursor.execute("""
            SELECT COUNT(*) FROM tv_retail_com
            WHERE DATE(crawl_datetime::timestamp) = %s
            AND (main_rank > 1000 OR bsr_rank > 1000)
        """, (target_date,))
        rank_anomalies = cursor.fetchone()[0] or 0

        layer3_total = layer2_total
        layer3_anomalies = price_anomalies + rank_anomalies

        layer3 = {
            'name': '이상치/특수 케이스',
            'description': '통계적 이상치 탐지 및 특수 패턴 분석',
            'total_checked': layer3_total,
            'passed': layer3_total - layer3_anomalies,
            'failed': layer3_anomalies,
            'price_anomalies': price_anomalies,
            'rank_anomalies': rank_anomalies,
            'pass_rate': round(((layer3_total - layer3_anomalies) / layer3_total * 100), 1) if layer3_total > 0 else 0,
            'status': 'OK' if layer3_anomalies < layer3_total * 0.02 else 'WARNING'
        }

        # ============================================================
        # Layer 4: 문맥/의미 검증 (LLM 감성분석 결과 확인)
        # ============================================================
        cursor.execute("""
            SELECT
                COUNT(*) as total,
                COUNT(s.id) as analyzed
            FROM tv_retail_com r
            LEFT JOIN tv_retail_sentiment s ON r.id = s.retail_com_id
            WHERE DATE(r.crawl_datetime::timestamp) = %s
        """, (target_date,))
        sentiment_result = cursor.fetchone()
        sentiment_total = sentiment_result[0] if sentiment_result else 0
        sentiment_analyzed = sentiment_result[1] if sentiment_result else 0

        layer4 = {
            'name': '문맥/의미 검증',
            'description': 'LLM 기반 감성분석 및 문맥 검증',
            'total_checked': sentiment_total,
            'passed': sentiment_analyzed,
            'failed': sentiment_total - sentiment_analyzed,
            'pass_rate': round((sentiment_analyzed / sentiment_total * 100), 1) if sentiment_total > 0 else 0,
            'status': 'OK' if sentiment_analyzed >= sentiment_total * 0.9 else 'WARNING'
        }

        # ============================================================
        # Layer 5: 전문가 검수 (수동 검토 대기 건수)
        # ============================================================
        pending_review = layer3_anomalies + (sentiment_total - sentiment_analyzed)

        layer5 = {
            'name': '전문가 검수',
            'description': '자동 검증 실패 항목에 대한 수동 전문가 검토',
            'pending_review': pending_review,
            'approved': 0,
            'rejected': 0,
            'status': 'PENDING' if pending_review > 0 else 'OK'
        }

    # ============================================================
    # Summary 계산
    # ============================================================
    total_raw = layer1_total
    total_passed_all_layers = min(
        layer1['total_records'],
        layer2['passed'],
        layer3['passed'],
        layer4['passed']
    )

    summary = {
        'total_raw_data': total_raw,
        'total_trusted_data': max(0, total_passed_all_layers),
        'overall_pass_rate': round((total_passed_all_layers / total_raw * 100), 1) if total_raw > 0 else 0,
        'pending_review': pending_review,
        'collection_sources': len(layer1_checks),
        'last_updated': datetime.now().isoformat()
    }

    return {
        'layers': {
            'layer1': layer1,
            'layer2': layer2,
            'layer3': layer3,
            'layer4': layer4,
            'layer5': layer5,
        },
        'summary': summary,
    }


def get_ds_dashboard_stats(target_date):
    """DS 대시보드 통계 조회 -- Layer 1 API 호출 기반

    Returns:
        dict with keys: layer_status, passed_layers, warning_layers, failed_layers
    """
    from apps.ds.ds_layer1.collection.api import layer_stats as ds_layer1_stats
    from django.test import RequestFactory
    import json

    factory = RequestFactory()
    fake_request = factory.get(f'/api/ds/layer1/stats/?date={target_date}')
    layer1_response = ds_layer1_stats(fake_request)
    layer1_data = layer1_response.content.decode('utf-8')
    layer1_json = json.loads(layer1_data)

    total_completion_rate = layer1_json.get('summary', {}).get('total_completion_rate', 0)

    results = layer1_json.get('results', [])
    success_count = sum(1 for r in results if r.get('status') == 'success')
    warning_count = sum(1 for r in results if r.get('status') == 'warning')
    danger_count = sum(1 for r in results if r.get('status') == 'danger')
    pending_count = sum(1 for r in results if r.get('status') in ['pending', 'collecting'])

    layer_status = {}
    passed_layers = 0
    warning_layers = 0
    failed_layers = 0

    # Layer 1 상태 결정
    if total_completion_rate >= 100:
        layer_status['layer1'] = 'success'
        passed_layers += 1
    elif pending_count == len(results):
        layer_status['layer1'] = 'pending'
        warning_layers += 1
    else:
        layer_status['layer1'] = 'danger'
        failed_layers += 1

    # Layer 2-5: 기본 pending 상태 (아직 구현 안됨)
    for i in range(2, 6):
        layer_status[f'layer{i}'] = 'pending'
        warning_layers += 1

    return {
        'layer_status': layer_status,
        'passed_layers': passed_layers,
        'warning_layers': warning_layers,
        'failed_layers': failed_layers,
    }


def check_health():
    """DX/DS 데이터베이스 연결 상태 확인

    Returns:
        dict with keys: dx, ds (각각 'connected' | 'error')
    """
    from apps.common.db import get_dx_connection, get_ds_connection

    db_status = {}

    try:
        conn = get_dx_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        cursor.close()
        conn.close()
        db_status['dx'] = 'connected'
    except Exception:
        db_status['dx'] = 'error'

    try:
        conn = get_ds_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        cursor.close()
        conn.close()
        db_status['ds'] = 'connected'
    except Exception:
        db_status['ds'] = 'error'

    return db_status
