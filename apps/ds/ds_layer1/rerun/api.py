"""
DS Layer 1 — 크롤러 재실행 API
request 파싱 + services 호출 + JsonResponse 반환
"""

from django.http import JsonResponse
from apps.common.response import safe_error
from . import services
import json


def rerun_crawler(request):
    """SSM을 통해 EC2 인스턴스에서 크롤러 재실행 API"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST 요청만 허용됩니다.'}, status=405)

    try:
        body = json.loads(request.body)
    except:
        return JsonResponse({'error': '잘못된 요청 형식입니다.'}, status=400)

    retailer = body.get('retailer')
    crawl_date = body.get('crawl_date')
    created_id = request.user.username if request.user.is_authenticated else None

    if not retailer or not crawl_date:
        return JsonResponse({'error': '리테일러, 날짜가 필요합니다.'}, status=400)

    # 리테일러 정보 조회
    try:
        info = services.get_retailer_info(retailer)
    except Exception as e:
        return safe_error(e, 'db')

    if not info:
        return JsonResponse({'error': '해당 리테일러를 찾을 수 없습니다.'}, status=404)

    if not info['instance_id']:
        return JsonResponse({'error': '이 리테일러는 instance_id가 없어 재실행할 수 없습니다.'}, status=400)

    if not info['schedule_name']:
        return JsonResponse({'error': '이 리테일러는 schedule_name이 등록되지 않았습니다.'}, status=400)

    # SSM 명령 실행
    try:
        command_id = services.execute_ssm_command(
            info['instance_id'], info['instance_region'],
            info['schedule_name'], retailer, crawl_date
        )
    except Exception as e:
        return safe_error(e)

    # 재실행 로그 저장 & 배치 자동 생성
    try:
        services.save_rerun_log(
            info['retailer_id'], retailer, crawl_date,
            info['schedule_name'], created_id,
            info['instance_id'], command_id,
            info['region_timezone'],
            request.user.username
        )
    except Exception as e:
        return safe_error(e, 'save')

    return JsonResponse({
        'success': True,
        'message': f'{retailer} 크롤러 재실행이 요청되었습니다.',
        'command_id': command_id,
        'instance_id': info['instance_id'],
        'retailer': retailer,
        'crawl_date': crawl_date,
        'schedule_name': info['schedule_name']
    })
