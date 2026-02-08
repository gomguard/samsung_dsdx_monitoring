"""
메인 대시보드 API
전체 레이어의 검수 현황을 종합하여 제공
"""

from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from datetime import datetime, timedelta
from apps.common.db import get_dx_connection
from apps.common.dx_schedules import load_collection_schedules, get_schedules_by_type
from config.config import S3_CONFIG
import json
import uuid
import re
import boto3
from botocore.exceptions import ClientError


def cleanup_orphan_files(cursor, object_document_id, content):
    """content에 없는 파일을 soft delete + S3 삭제"""
    if not object_document_id:
        return

    # DB에서 이 문서의 활성 파일 목록 조회
    cursor.execute("""
        SELECT file_id, file_name, file_path FROM monitoring_files
        WHERE object_document_id = %s AND is_del = false
    """, (object_document_id,))
    files = cursor.fetchall()

    if not files:
        return

    # content에 포함되지 않은 파일 찾기
    orphans = [f for f in files if f[1] not in (content or '')]

    if not orphans:
        return

    # DB soft delete
    orphan_ids = [f[0] for f in orphans]
    cursor.execute("""
        UPDATE monitoring_files SET is_del = true
        WHERE file_id = ANY(%s)
    """, (orphan_ids,))

    # S3 삭제
    try:
        s3_client = boto3.client(
            's3',
            region_name=S3_CONFIG['region'],
            aws_access_key_id=S3_CONFIG['access_key'],
            aws_secret_access_key=S3_CONFIG['secret_key']
        )
        for f in orphans:
            s3_key = f'{f[2]}/{f[1]}'  # file_path + / + file_name
            s3_client.delete_object(Bucket=S3_CONFIG['bucket'], Key=s3_key)
    except Exception:
        pass  # S3 삭제 실패해도 DB는 이미 처리됨


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
        # 수집 현황 (CSV 기반 스케줄)
        # ============================================================
        all_schedules = load_collection_schedules()
        # daily 스케줄만 필터링
        daily_schedules = [s for s in all_schedules if s['schedule_type'] == 'daily']
        for schedule in daily_schedules[:5]:  # 상위 5개만
            data['collection_status'].append({
                'name': schedule['name'],
                'category': schedule['category'],
                'schedule_type': schedule['schedule_type'],
                'us_start_hour': schedule['us_start_hour'],
                'description': schedule['description']
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
    """수집 스케줄 API (CSV 기반)"""
    check_type = request.GET.get('check_type')
    category = request.GET.get('category')

    if check_type:
        schedules = get_schedules_by_type(check_type, category)
    else:
        schedules = load_collection_schedules()

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
        if total_completion_rate >= 100:
            data['layer_status']['layer1'] = 'success'
            data['passed_layers'] += 1
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


# ============================================================
# 문서 CRUD API
# ============================================================

def dx_documents_list(request):
    """문서 목록 조회 API (카테고리별)"""
    category_id = request.GET.get('category_id', '')

    if not category_id:
        return JsonResponse({'success': False, 'error': '카테고리 ID가 필요합니다.'})

    try:
        conn = get_dx_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT document_id, category_id, title, created_id,
                   TO_CHAR(updated_at AT TIME ZONE 'Asia/Seoul', 'YYYY-MM-DD HH24:MI') as updated_at
            FROM monitoring_documents
            WHERE category_id = %s AND is_del = false
            ORDER BY created_at DESC
        """, (category_id,))
        columns = [desc[0] for desc in cursor.description]
        documents = [dict(zip(columns, row)) for row in cursor.fetchall()]
        cursor.close()
        conn.close()

        return JsonResponse({'success': True, 'documents': documents, 'total': len(documents)})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


def dx_document_detail(request):
    """문서 상세 조회 API"""
    document_id = request.GET.get('document_id', '')

    if not document_id:
        return JsonResponse({'success': False, 'error': '문서 ID가 필요합니다.'})

    try:
        conn = get_dx_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT d.document_id, d.category_id, d.title, d.content, d.object_document_id,
                   d.created_id, TO_CHAR(d.created_at AT TIME ZONE 'Asia/Seoul', 'YYYY-MM-DD HH24:MI') as created_at,
                   d.updated_id, TO_CHAR(d.updated_at AT TIME ZONE 'Asia/Seoul', 'YYYY-MM-DD HH24:MI') as updated_at,
                   COALESCE(c.category_type, 1) as category_type
            FROM monitoring_documents d
            LEFT JOIN monitoring_document_categories c ON d.category_id = c.category_id
            WHERE d.document_id = %s AND d.is_del = false
        """, (document_id,))
        columns = [desc[0] for desc in cursor.description]
        row = cursor.fetchone()
        cursor.close()
        conn.close()

        if not row:
            return JsonResponse({'success': False, 'error': '문서를 찾을 수 없습니다.'})

        document = dict(zip(columns, row))
        return JsonResponse({'success': True, 'document': document})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@login_required
@require_POST
def dx_document_create(request):
    """문서 생성 API"""
    try:
        data = json.loads(request.body)
        category_id = data.get('category_id', '').strip()
        title = data.get('title', '').strip()
        content = data.get('content', '')
        object_document_id = data.get('object_document_id', '').strip()

        if not category_id:
            return JsonResponse({'success': False, 'error': '카테고리를 선택하세요.'})
        if not title:
            return JsonResponse({'success': False, 'error': '제목을 입력하세요.'})

        now = datetime.now()
        conn = get_dx_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO monitoring_documents
                (category_id, title, content, object_document_id, created_id, created_at, updated_id, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING document_id, object_document_id
        """, (category_id, title, content, object_document_id or None,
              request.user.username, now, request.user.username, now))
        result = cursor.fetchone()
        # 카테고리 타입 조회 (2=파일저장 모드면 고아 파일 정리 건너뜀)
        cursor.execute("SELECT category_type FROM monitoring_document_categories WHERE category_id = %s", (category_id,))
        cat_row = cursor.fetchone()
        category_type = cat_row[0] if cat_row else 1
        if category_type != 2:
            cleanup_orphan_files(cursor, object_document_id, content)
        conn.commit()
        cursor.close()
        conn.close()

        return JsonResponse({
            'success': True,
            'document_id': result[0],
            'object_document_id': result[1],
            'message': '문서가 저장되었습니다.'
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@login_required
@require_POST
def dx_document_update(request, document_id):
    """문서 수정 API"""
    try:
        data = json.loads(request.body)
        title = data.get('title', '').strip()
        content = data.get('content', '')

        if not title:
            return JsonResponse({'success': False, 'error': '제목을 입력하세요.'})

        now = datetime.now()
        conn = get_dx_connection()
        cursor = conn.cursor()
        # object_document_id, category_type 조회
        cursor.execute("""
            SELECT d.object_document_id, COALESCE(c.category_type, 1)
            FROM monitoring_documents d
            LEFT JOIN monitoring_document_categories c ON d.category_id = c.category_id
            WHERE d.document_id = %s AND d.is_del = false
        """, (document_id,))
        row = cursor.fetchone()
        obj_doc_id = row[0] if row else None
        category_type = row[1] if row else 1

        cursor.execute("""
            UPDATE monitoring_documents
            SET title = %s, content = %s, updated_id = %s, updated_at = %s
            WHERE document_id = %s AND is_del = false
        """, (title, content, request.user.username, now, document_id))
        # 카테고리 타입 2(파일저장)면 고아 파일 정리 건너뜀
        if category_type != 2:
            cleanup_orphan_files(cursor, obj_doc_id, content)
        conn.commit()
        cursor.close()
        conn.close()

        return JsonResponse({'success': True, 'message': '문서가 수정되었습니다.'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@login_required
@require_POST
def dx_document_delete(request, document_id):
    """문서 삭제 API (soft delete + 파일 정리)"""
    try:
        now = datetime.now()
        conn = get_dx_connection()
        cursor = conn.cursor()

        # object_document_id 조회
        cursor.execute("""
            SELECT object_document_id FROM monitoring_documents
            WHERE document_id = %s
        """, (document_id,))
        row = cursor.fetchone()
        obj_doc_id = row[0] if row else None

        # 문서 soft delete
        cursor.execute("""
            UPDATE monitoring_documents
            SET is_del = true, updated_id = %s, updated_at = %s
            WHERE document_id = %s
        """, (request.user.username, now, document_id))

        # 연결된 파일 전체 삭제
        if obj_doc_id:
            # 파일 목록 조회
            cursor.execute("""
                SELECT file_name, file_path FROM monitoring_files
                WHERE object_document_id = %s AND is_del = false
            """, (obj_doc_id,))
            files = cursor.fetchall()

            # DB soft delete
            cursor.execute("""
                UPDATE monitoring_files SET is_del = true
                WHERE object_document_id = %s AND is_del = false
            """, (obj_doc_id,))

            # S3 삭제
            if files:
                try:
                    s3_client = boto3.client(
                        's3',
                        region_name=S3_CONFIG['region'],
                        aws_access_key_id=S3_CONFIG['access_key'],
                        aws_secret_access_key=S3_CONFIG['secret_key']
                    )
                    for f in files:
                        s3_key = f'{f[1]}/{f[0]}'  # file_path/file_name
                        s3_client.delete_object(Bucket=S3_CONFIG['bucket'], Key=s3_key)
                except Exception:
                    pass

        conn.commit()
        cursor.close()
        conn.close()

        return JsonResponse({'success': True, 'message': '문서가 삭제되었습니다.'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@login_required
@require_POST
def dx_document_upload(request):
    """문서 이미지 업로드 API (S3)"""
    try:
        file = request.FILES.get('file')
        object_document_id = request.POST.get('object_document_id', '').strip()

        if not file:
            return JsonResponse({'success': False, 'error': '파일이 없습니다.'})
        if not object_document_id:
            return JsonResponse({'success': False, 'error': 'object_document_id가 필요합니다.'})

        # UUID 파일명 생성
        ext = file.name.rsplit('.', 1)[-1].lower() if '.' in file.name else 'png'
        s3_file_name = f'{uuid.uuid4()}.{ext}'
        # 경로와 파일명 분리 저장
        date_part = object_document_id.split('-')[0]  # 20260207
        year = date_part[:4]       # 2026
        year_month = date_part[:6] # 202602
        s3_path = f'dx-documents/{year}/{year_month}/{object_document_id}'
        s3_key = f'{s3_path}/{s3_file_name}'

        # S3 업로드
        s3_client = boto3.client(
            's3',
            region_name=S3_CONFIG['region'],
            aws_access_key_id=S3_CONFIG['access_key'],
            aws_secret_access_key=S3_CONFIG['secret_key']
        )

        s3_client.upload_fileobj(
            file,
            S3_CONFIG['bucket'],
            s3_key,
            ExtraArgs={'ContentType': file.content_type}
        )

        # 파일 테이블에 저장
        now = datetime.now()
        conn = get_dx_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO monitoring_files
                (object_document_id, original_file_name, file_name, file_path,
                 file_size, file_type, created_at, created_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING file_id
        """, (object_document_id, file.name, s3_file_name, s3_path,
              file.size, file.content_type, now, request.user.username))
        file_id = cursor.fetchone()[0]
        conn.commit()
        cursor.close()
        conn.close()

        # 프록시 URL 반환 (키 노출 없음, 만료 없음)
        proxy_url = f'/api/dx/documents/file/{s3_file_name}'

        return JsonResponse({
            'success': True,
            'file_id': file_id,
            'url': proxy_url
        })
    except ClientError as e:
        return JsonResponse({'success': False, 'error': f'S3 오류: {str(e)}'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@login_required
def dx_document_file(request, file_name):
    """문서 이미지 프록시 - S3 pre-signed URL로 리다이렉트"""
    from django.http import HttpResponseRedirect

    try:
        conn = get_dx_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT file_name, file_path FROM monitoring_files
            WHERE file_name = %s AND is_del = false
        """, (file_name,))
        row = cursor.fetchone()
        cursor.close()
        conn.close()

        if not row:
            return JsonResponse({'success': False, 'error': '파일을 찾을 수 없습니다.'}, status=404)

        s3_key = f'{row[1]}/{row[0]}'  # file_path/file_name

        s3_client = boto3.client(
            's3',
            region_name=S3_CONFIG['region'],
            aws_access_key_id=S3_CONFIG['access_key'],
            aws_secret_access_key=S3_CONFIG['secret_key']
        )

        url = s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': S3_CONFIG['bucket'], 'Key': s3_key},
            ExpiresIn=3600
        )

        return HttpResponseRedirect(url)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@require_POST
def dx_document_file_delete(request, file_id):
    """첨부파일 개별 삭제 API (DB soft delete + S3 삭제)"""
    try:
        conn = get_dx_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT file_name, file_path FROM monitoring_files
            WHERE file_id = %s AND is_del = false
        """, (file_id,))
        row = cursor.fetchone()
        if not row:
            cursor.close()
            conn.close()
            return JsonResponse({'success': False, 'error': '파일을 찾을 수 없습니다.'})

        # DB soft delete
        cursor.execute("UPDATE monitoring_files SET is_del = true WHERE file_id = %s", (file_id,))
        conn.commit()
        cursor.close()
        conn.close()

        # S3 삭제
        try:
            s3_key = f'{row[1]}/{row[0]}'
            s3_client = boto3.client(
                's3',
                region_name=S3_CONFIG['region'],
                aws_access_key_id=S3_CONFIG['access_key'],
                aws_secret_access_key=S3_CONFIG['secret_key']
            )
            s3_client.delete_object(Bucket=S3_CONFIG['bucket'], Key=s3_key)
        except Exception:
            pass

        return JsonResponse({'success': True, 'message': '파일이 삭제되었습니다.'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@login_required
def dx_document_files(request):
    """문서 첨부파일 목록 조회 API"""
    object_document_id = request.GET.get('object_document_id', '')

    if not object_document_id:
        return JsonResponse({'success': False, 'error': 'object_document_id가 필요합니다.'})

    try:
        conn = get_dx_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT file_id, original_file_name, file_name, file_size, file_type,
                   TO_CHAR(created_at AT TIME ZONE 'Asia/Seoul', 'YYYY-MM-DD HH24:MI') as created_at
            FROM monitoring_files
            WHERE object_document_id = %s AND is_del = false
            ORDER BY created_at
        """, (object_document_id,))
        columns = [desc[0] for desc in cursor.description]
        files = [dict(zip(columns, row)) for row in cursor.fetchall()]
        cursor.close()
        conn.close()

        return JsonResponse({'success': True, 'files': files})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})
