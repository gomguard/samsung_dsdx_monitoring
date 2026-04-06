"""
메인 대시보드 API
전체 레이어의 검수 현황을 종합하여 제공
"""

from django.http import JsonResponse
from apps.common.response import log_error
from datetime import datetime, timedelta
from apps.common.dx_schedules import load_collection_schedules, get_schedules_by_type
from apps.main.api.services import get_dashboard_stats, check_health


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
        result = get_dashboard_stats(target_date)
        data['layers'] = result['layers']
        data['summary'] = result['summary']

        # 수집 현황 (CSV 기반 스케줄)
        all_schedules = load_collection_schedules()
        daily_schedules = [s for s in all_schedules if s['schedule_type'] == 'daily']
        for schedule in daily_schedules[:5]:
            data['collection_status'].append({
                'name': schedule['name'],
                'category': schedule['category'],
                'schedule_type': schedule['schedule_type'],
                'us_start_hour': schedule['us_start_hour'],
                'description': schedule['description']
            })

    except Exception as e:
        data['error'] = log_error(e)
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


def health_check(request):
    """시스템 상태 체크 API"""
    status = {
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'database': {}
    }

    db_status = check_health()
    status['database'] = db_status

    if 'error' in db_status.values():
        status['status'] = 'degraded'

    return JsonResponse(status)
