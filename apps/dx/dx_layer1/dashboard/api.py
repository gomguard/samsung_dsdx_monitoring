"""
Layer 1 API: 기본 통계 검수 (Foundational Integrity Check)
- 8개 메뉴 서비스의 get_layer1_stats()를 호출하여 통합 결과 반환
"""

from django.http import JsonResponse
from datetime import datetime, timedelta
from apps.common.db import dx_connection
from apps.common.response import log_error

from apps.dx.dx_layer1.retail import services as retail_svc
from apps.dx.dx_layer1.sentiment import services as sentiment_svc
from apps.dx.dx_layer1.youtube import services as youtube_svc
from apps.dx.dx_layer1.market_trend import services as market_trend_svc
from apps.dx.dx_layer1.market_demand import services as market_demand_svc
from apps.dx.dx_layer1.market_competitor import services as market_competitor_svc
from apps.dx.dx_layer1.market_competitor_event import services as market_competitor_event_svc
from apps.dx.dx_layer1.market_promotion import services as market_promotion_svc
from apps.common.dx_schedules import load_collection_schedules


# 리테일러 설정 (thresholds 표시용)
EXPECTED_PER_RETAILER = 300
OK_THRESHOLD = 200

# check_type → 서비스 모듈 매핑
_SERVICE_MAP = {
    'retail': retail_svc,
    'sentiment': sentiment_svc,
    'youtube': youtube_svc,
    'market_trend': market_trend_svc,
    'market_demand': market_demand_svc,
    'market_competitor': market_competitor_svc,
    'market_competitor_event': market_competitor_event_svc,
    'market_promotion': market_promotion_svc,
}


def _get_active_services():
    """스케줄 DB에서 활성 서비스 목록과 daily 여부를 동적으로 구성"""
    schedules = load_collection_schedules()
    seen = set()
    service_order = []
    daily_types = set()

    for s in schedules:
        ct = s['check_type']
        if ct in seen or ct not in _SERVICE_MAP:
            continue
        seen.add(ct)
        service_order.append((ct, _SERVICE_MAP[ct]))
        if s['schedule_type'] == 'daily':
            daily_types.add(ct)

    return service_order, daily_types


def layer_stats(request):
    """Layer 1 통계 API - 8개 서비스 오케스트레이션"""

    date_str = request.GET.get('date')
    check_type_filter = request.GET.get('check_type')
    now = datetime.now()
    today = now.date()

    if date_str:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    else:
        target_date = today - timedelta(days=1)

    results = {
        'timestamp': datetime.now().isoformat(),
        'target_date': str(target_date),
        'today': str(today),
        'layer': 1,
        'name': '기본 통계 검수',
        'checks': [],
        'failed_items': [],
        'thresholds': {
            'expected': EXPECTED_PER_RETAILER,
            'ok': OK_THRESHOLD,
            'description': f'정상: {OK_THRESHOLD}건 이상 | 위험: {OK_THRESHOLD}건 미만'
        },
        'summary': {
            'total_checked': 0,
            'passed': 0,
            'failed': 0,
            'pass_rate': 0,
            'status': 'OK'
        }
    }

    try:
        with dx_connection() as (conn, cursor):
            service_order, daily_types = _get_active_services()
            comp_batch_id = None

            for check_type, svc in service_order:
                if check_type_filter and check_type_filter != check_type:
                    continue

                # market_competitor_event는 competitor에서 얻은 batch_id 전달
                if check_type == 'market_competitor_event':
                    svc_result = svc.get_layer1_stats(cursor, target_date, now, comp_batch_id=comp_batch_id)
                else:
                    svc_result = svc.get_layer1_stats(cursor, target_date, now)

                # market_competitor 서비스가 comp_batch_id를 반환하면 저장
                if check_type == 'market_competitor' and 'comp_batch_id' in svc_result:
                    comp_batch_id = svc_result['comp_batch_id']

                check_data = svc_result['check']
                check_data['display_group'] = 'daily' if check_type in daily_types else 'periodic'
                results['checks'].append(check_data)
                results['failed_items'].extend(svc_result.get('failed_items', []))

        # Summary 계산 (대시보드 전용 - 섹션 페이지에서는 불필요)
        if not check_type_filter:
            check_items = []
            for check in results['checks']:
                check_type = check.get('check_type', '')
                if check_type in daily_types:
                    is_target = True
                else:
                    is_target = check.get('is_target_date', False)
                check_items.append({'status': check['status'], 'is_target': is_target})

            target_items = [item for item in check_items if item['is_target']]
            target_statuses = [item['status'] for item in target_items]
            completed_statuses = [s for s in target_statuses if s not in ('PENDING', 'COLLECTING', 'ANALYZING')]

            passed = len([s for s in completed_statuses if s == 'OK'])
            failed = len([s for s in completed_statuses if s == 'CRITICAL'])

            results['summary'] = {
                'total_checked': len(target_items),
                'total_completed': len(completed_statuses),
                'passed': passed,
                'failed': failed,
                'pass_rate': round((passed / len(target_items) * 100), 1) if target_items else 0,
                'status': 'CRITICAL' if failed > 0 else 'OK'
            }

    except Exception as e:
        results['error'] = log_error(e)
        results['summary']['status'] = 'ERROR'

    return JsonResponse(results)
