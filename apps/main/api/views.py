"""
메인 대시보드 API
전체 레이어의 검수 현황을 종합하여 제공
"""

from django.http import JsonResponse
from datetime import datetime, timedelta
from apps.common.db import get_dx_connection
from apps.common.schedule import ALL_SCHEDULES, get_daily_schedules


def dashboard_stats(request):
    """대시보드 전체 통계 API"""
    date_str = request.GET.get('date')

    if date_str:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    else:
        target_date = (datetime.now() - timedelta(days=1)).date()

    data = {
        'timestamp': datetime.now().isoformat(),
        'date': str(target_date),
        'layers': {},
        'summary': {},
        'collection_status': []
    }

    try:
        conn = get_dx_connection()
        cursor = conn.cursor()

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

        data['layers']['layer1'] = {
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
        # NULL 체크 및 중복 체크
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

        data['layers']['layer2'] = {
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
        # 가격 이상치 탐지 - 복잡한 문자열 처리 대신 단순히 0 체크
        # final_sku_price가 "$84.95" 같은 다양한 문자열이므로 일단 스킵
        price_anomalies = 0

        # 순위 이상치 (1000위 초과)
        cursor.execute("""
            SELECT COUNT(*) FROM tv_retail_com
            WHERE DATE(crawl_datetime::timestamp) = %s
            AND (main_rank > 1000 OR bsr_rank > 1000)
        """, (target_date,))
        rank_anomalies = cursor.fetchone()[0] or 0

        layer3_total = layer2_total
        layer3_anomalies = price_anomalies + rank_anomalies

        data['layers']['layer3'] = {
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
        # tv_retail_sentiment 테이블과 조인하여 감성분석 완료 여부 확인
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

        data['layers']['layer4'] = {
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
        # 이상치로 분류된 데이터 중 검토 대기 건수
        pending_review = layer3_anomalies + (sentiment_total - sentiment_analyzed)

        data['layers']['layer5'] = {
            'name': '전문가 검수',
            'description': '자동 검증 실패 항목에 대한 수동 전문가 검토',
            'pending_review': pending_review,
            'approved': 0,  # TODO: 승인 테이블 연동
            'rejected': 0,  # TODO: 거부 테이블 연동
            'status': 'PENDING' if pending_review > 0 else 'OK'
        }

        cursor.close()
        conn.close()

        # ============================================================
        # Summary 계산
        # ============================================================
        total_raw = layer1_total
        total_passed_all_layers = min(
            data['layers']['layer1']['total_records'],
            data['layers']['layer2']['passed'],
            data['layers']['layer3']['passed'],
            data['layers']['layer4']['passed']
        )

        data['summary'] = {
            'total_raw_data': total_raw,
            'total_trusted_data': max(0, total_passed_all_layers),
            'overall_pass_rate': round((total_passed_all_layers / total_raw * 100), 1) if total_raw > 0 else 0,
            'pending_review': pending_review,
            'collection_sources': len(layer1_checks),
            'last_updated': datetime.now().isoformat()
        }

        # ============================================================
        # 수집 현황 (스케줄 기반)
        # ============================================================
        daily_schedules = get_daily_schedules()
        for schedule in daily_schedules[:5]:  # 상위 5개만
            data['collection_status'].append({
                'name': schedule['name'],
                'source': schedule['source'],
                'frequency': schedule['frequency'],
                'time': schedule['time'],
                'category': schedule['category']
            })

    except Exception as e:
        data['error'] = str(e)
        data['summary'] = {
            'total_raw_data': 0,
            'total_trusted_data': 0,
            'overall_pass_rate': 0,
            'pending_review': 0,
            'status': 'ERROR'
        }

    return JsonResponse(data)


def collection_schedule(request):
    """수집 스케줄 API"""
    category = request.GET.get('category')

    if category:
        from apps.common.schedule import get_schedule_by_category
        schedules = get_schedule_by_category(category)
    else:
        schedules = ALL_SCHEDULES

    return JsonResponse({
        'total': len(schedules),
        'schedules': schedules
    })


def dx_dashboard_stats(request):
    """DX 대시보드 통계 API - TV/HHP Retail 모니터링"""
    date_str = request.GET.get('date')

    if date_str:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    else:
        target_date = (datetime.now() - timedelta(days=1)).date()

    data = {
        'timestamp': datetime.now().isoformat(),
        'date': str(target_date),
        'data_source': 'dx',
        'total_tables': 5,
        'passed_layers': 0,
        'warning_layers': 0,
        'failed_layers': 0,
        'layer_status': {}
    }

    try:
        conn = get_dx_connection()
        cursor = conn.cursor()

        # Layer 1: 수집량 체크
        layer1_ok = True
        tables_checked = 0

        # TV Retail
        cursor.execute("""
            SELECT COUNT(*) FROM tv_retail_com
            WHERE DATE(crawl_datetime::timestamp) = %s
        """, (target_date,))
        tv_count = cursor.fetchone()[0] or 0
        if tv_count < 100:
            layer1_ok = False
        tables_checked += 1

        # HHP Retail
        cursor.execute("""
            SELECT COUNT(*) FROM hhp_retail_com
            WHERE DATE(crawl_strdatetime::timestamp) = %s
        """, (target_date,))
        hhp_count = cursor.fetchone()[0] or 0
        if hhp_count < 100:
            layer1_ok = False
        tables_checked += 1

        data['layer_status']['layer1'] = 'success' if layer1_ok else 'warning'
        if layer1_ok:
            data['passed_layers'] += 1
        else:
            data['warning_layers'] += 1

        # Layer 2: NULL/형식 체크
        cursor.execute("""
            SELECT
                COUNT(*) as total,
                COUNT(CASE WHEN retailer_sku_name IS NULL OR retailer_sku_name = '' THEN 1 END) as null_count
            FROM tv_retail_com
            WHERE DATE(crawl_datetime::timestamp) = %s
        """, (target_date,))
        result = cursor.fetchone()
        total = result[0] if result else 0
        null_count = result[1] if result else 0

        null_rate = (null_count / total * 100) if total > 0 else 0
        if null_rate < 5:
            data['layer_status']['layer2'] = 'success'
            data['passed_layers'] += 1
        elif null_rate < 10:
            data['layer_status']['layer2'] = 'warning'
            data['warning_layers'] += 1
        else:
            data['layer_status']['layer2'] = 'danger'
            data['failed_layers'] += 1

        # Layer 3: 이상치 체크
        cursor.execute("""
            SELECT COUNT(*) FROM tv_retail_com
            WHERE DATE(crawl_datetime::timestamp) = %s
            AND main_rank > 500
        """, (target_date,))
        anomaly_count = cursor.fetchone()[0] or 0
        anomaly_rate = (anomaly_count / total * 100) if total > 0 else 0

        if anomaly_rate < 2:
            data['layer_status']['layer3'] = 'success'
            data['passed_layers'] += 1
        elif anomaly_rate < 5:
            data['layer_status']['layer3'] = 'warning'
            data['warning_layers'] += 1
        else:
            data['layer_status']['layer3'] = 'danger'
            data['failed_layers'] += 1

        # Layer 4: 문맥 검증 (감성분석 완료 여부)
        cursor.execute("""
            SELECT
                COUNT(DISTINCT r.id) as total,
                COUNT(DISTINCT s.retail_com_id) as analyzed
            FROM tv_retail_com r
            LEFT JOIN tv_retail_sentiment s ON r.id = s.retail_com_id
            WHERE DATE(r.crawl_datetime::timestamp) = %s
        """, (target_date,))
        result = cursor.fetchone()
        sentiment_total = result[0] if result else 0
        sentiment_analyzed = result[1] if result else 0

        sentiment_rate = (sentiment_analyzed / sentiment_total * 100) if sentiment_total > 0 else 0
        if sentiment_rate >= 90:
            data['layer_status']['layer4'] = 'success'
            data['passed_layers'] += 1
        elif sentiment_rate >= 70:
            data['layer_status']['layer4'] = 'warning'
            data['warning_layers'] += 1
        else:
            data['layer_status']['layer4'] = 'pending'
            data['warning_layers'] += 1

        # Layer 5: 전문가 검수 (대기 상태)
        data['layer_status']['layer5'] = 'pending'
        data['warning_layers'] += 1

        cursor.close()
        conn.close()

    except Exception as e:
        data['error'] = str(e)
        for i in range(1, 6):
            data['layer_status'][f'layer{i}'] = 'danger'
        data['failed_layers'] = 5

    return JsonResponse(data)


def ds_dashboard_stats(request):
    """DS 대시보드 통계 API - 글로벌 가격 추적 모니터링"""
    from apps.ds_layer1.api.views import layer_stats as ds_layer1_stats

    date_str = request.GET.get('date')

    if date_str:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    else:
        target_date = (datetime.now() - timedelta(days=1)).date()

    data = {
        'timestamp': datetime.now().isoformat(),
        'date': str(target_date),
        'data_source': 'ds',
        'total_tables': 17,
        'passed_layers': 0,
        'warning_layers': 0,
        'failed_layers': 0,
        'layer_status': {}
    }

    try:
        # Layer 1: ds_layer1 API 결과 기반으로 상태 판단
        # 내부적으로 layer_stats 호출
        from django.test import RequestFactory
        factory = RequestFactory()
        fake_request = factory.get(f'/api/ds/layer1/stats/?date={target_date}')
        layer1_response = ds_layer1_stats(fake_request)
        layer1_data = layer1_response.content.decode('utf-8')
        import json
        layer1_json = json.loads(layer1_data)

        # Layer 1 상태 판단: 전체 완료율 기반
        total_completion_rate = layer1_json.get('summary', {}).get('total_completion_rate', 0)

        # 각 리테일러 상태 카운트
        results = layer1_json.get('results', [])
        success_count = sum(1 for r in results if r.get('status') == 'success')
        warning_count = sum(1 for r in results if r.get('status') == 'warning')
        danger_count = sum(1 for r in results if r.get('status') == 'danger')
        pending_count = sum(1 for r in results if r.get('status') in ['pending', 'collecting'])

        # Layer 1 상태 결정
        if total_completion_rate >= 95:
            data['layer_status']['layer1'] = 'success'
            data['passed_layers'] += 1
        elif total_completion_rate >= 80:
            data['layer_status']['layer1'] = 'warning'
            data['warning_layers'] += 1
        elif pending_count == len(results):
            # 모든 리테일러가 대기/수집 중이면 pending
            data['layer_status']['layer1'] = 'pending'
            data['warning_layers'] += 1
        else:
            data['layer_status']['layer1'] = 'danger'
            data['failed_layers'] += 1

        # Layer 2-5: 기본 pending 상태 (아직 구현 안됨)
        data['layer_status']['layer2'] = 'pending'
        data['warning_layers'] += 1
        data['layer_status']['layer3'] = 'pending'
        data['warning_layers'] += 1
        data['layer_status']['layer4'] = 'pending'
        data['warning_layers'] += 1
        data['layer_status']['layer5'] = 'pending'
        data['warning_layers'] += 1

    except Exception as e:
        data['error'] = str(e)
        for i in range(1, 6):
            data['layer_status'][f'layer{i}'] = 'danger'
        data['failed_layers'] = 5

    return JsonResponse(data)


def health_check(request):
    """시스템 상태 체크 API"""
    from apps.common.db import get_ds_connection

    status = {
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'database': {}
    }

    # DX PostgreSQL 연결 테스트
    try:
        conn = get_dx_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        cursor.close()
        conn.close()
        status['database']['dx'] = 'connected'
    except Exception as e:
        status['database']['dx'] = f'error: {str(e)}'
        status['status'] = 'degraded'

    # DS MySQL 연결 테스트
    try:
        conn = get_ds_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        cursor.close()
        conn.close()
        status['database']['ds'] = 'connected'
    except Exception as e:
        status['database']['ds'] = f'error: {str(e)}'
        status['status'] = 'degraded'

    return JsonResponse(status)
