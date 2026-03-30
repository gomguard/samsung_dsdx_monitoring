"""
DS Layer 1 - 크롤러 재실행 API
"""

from django.http import JsonResponse
import json
from apps.common.response import log_error
from . import rerun_services

def rerun_crawler(request):
    """크롤러 재실행 명령(SSM) 및 로그 수집 API"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST 요청만 허용됩니다.'}, status=405)

    try:
        data = json.loads(request.body)
        retailer = data.get('retailer')
        crawl_date = data.get('date')

        if not retailer or not crawl_date:
            return JsonResponse({'error': '파라미터가 모두 필요합니다.'}, status=400)

        info = rerun_services.get_retailer_info(retailer)
        if not info:
            return JsonResponse({'error': f'해당 리테일러({retailer})의 인스턴스 정보가 없습니다.'}, status=404)

        instance_id = info['instance_id']
        instance_region = info['instance_region']
        schedule_name = info['schedule_name']
        retailer_id = info['retailer_id']
        region_timezone = info['region_timezone']

        if not instance_id or not schedule_name:
            return JsonResponse({'error': '실행할 인스턴스 ID 또는 스케줄 이름이 설정되지 않았습니다.'}, status=400)

        # 1. AWS SSM 명령 실행 (Service 내에서 Adapter 호출)
        command_id = rerun_services.execute_ssm_command(
            instance_id, instance_region, schedule_name, retailer, crawl_date
        )

        # 2. 수행 기록 처리 (Service 내에서 시간 계산 후 Repo 호출)
        username = request.user.username if request.user.is_authenticated else 'system'
        user_id = request.user.id if request.user.is_authenticated else 0

        rerun_services.save_rerun_log(
            retailer_id=retailer_id,
            retailer=retailer,
            crawl_date=crawl_date,
            schedule_name=schedule_name,
            created_id=user_id,
            instance_id=instance_id,
            command_id=command_id,
            region_timezone=region_timezone,
            username=username
        )

        return JsonResponse({
            'success': True,
            'message': f'{retailer} 재실행 명령이 전송되었습니다.',
            'command_id': command_id
        })

    except Exception as e:
        return JsonResponse({'error': log_error(e)}, status=500)
