"""
인프라 모니터링 API: EC2 인스턴스 상태 조회 / 시작 / 종료
"""

import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST
from apps.common.targets import load_ec2_instances

logger = logging.getLogger(__name__)

try:
    import boto3
    from botocore.exceptions import ClientError, NoCredentialsError
    HAS_BOTO3 = True
except ImportError:
    HAS_BOTO3 = False

try:
    from config.config import SSM_CONFIG
except ImportError:
    SSM_CONFIG = {}


def _get_ec2_client(region):
    """리전별 EC2 클라이언트 생성"""
    if not HAS_BOTO3:
        return None
    if not SSM_CONFIG.get('access_key') or not SSM_CONFIG.get('secret_key'):
        return None
    return boto3.client(
        'ec2',
        region_name=region,
        aws_access_key_id=SSM_CONFIG['access_key'],
        aws_secret_access_key=SSM_CONFIG['secret_key'],
    )


@require_GET
def ec2_status(request):
    """EC2 인스턴스 상태 조회 — instance_id/region 미노출"""
    instances = load_ec2_instances()

    if not instances:
        return JsonResponse({'success': True, 'instances': []})

    # 리전별로 AWS 인스턴스 그룹핑
    region_map = {}
    for key, info in instances.items():
        if info['is_aws'] and info['instance_id'] and info['region']:
            region = info['region']
            if region not in region_map:
                region_map[region] = []
            region_map[region].append(info['instance_id'])

    # 리전별 describe_instances 병렬 호출
    state_map = {}

    def fetch_region(region, instance_ids):
        result = {}
        try:
            client = _get_ec2_client(region)
            if not client:
                for iid in instance_ids:
                    result[iid] = {'state': 'unknown'}
                return result

            response = client.describe_instances(InstanceIds=instance_ids)
            for reservation in response.get('Reservations', []):
                for inst in reservation.get('Instances', []):
                    iid = inst['InstanceId']
                    state = inst['State']['Name']
                    name = ''
                    for tag in inst.get('Tags', []):
                        if tag['Key'] == 'Name':
                            name = tag['Value']
                            break
                    result[iid] = {'state': state, 'name': name}
        except Exception as e:
            logger.error(f"EC2 describe_instances 실패 (region={region}): {e}")
            for iid in instance_ids:
                if iid not in result:
                    result[iid] = {'state': 'unknown'}
        return result

    with ThreadPoolExecutor(max_workers=len(region_map) or 1) as executor:
        futures = {
            executor.submit(fetch_region, region, ids): region
            for region, ids in region_map.items()
        }
        for future in as_completed(futures):
            state_map.update(future.result())

    # 응답 구성 — instance_id, region 미포함
    result = []
    for key, info in instances.items():
        instance_id = info['instance_id']
        entry = {
            'key': key,
            'region_name': info.get('region_name', ''),
            'retailers': info['retailers'],
            'is_aws': info['is_aws'],
            'state': 'N/A',
            'name': '',
        }

        if info['is_aws'] and instance_id in state_map:
            s = state_map[instance_id]
            entry['state'] = s.get('state', 'unknown')
            entry['name'] = s.get('name', '')

        result.append(entry)

    return JsonResponse({'success': True, 'instances': result})


@require_POST
def ec2_action(request):
    """EC2 인스턴스 시작/종료 — key 기반 검증, 관리자 전용"""
    # 관리자 권한 체크
    if not request.user.is_staff:
        return JsonResponse({'success': False}, status=403)

    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'success': False}, status=400)

    key = body.get('key')
    action = body.get('action')

    if not key or action not in ('start', 'stop'):
        return JsonResponse({'success': False}, status=400)

    # DB에 등록된 인스턴스인지 검증
    instances = load_ec2_instances()
    info = instances.get(key)
    if not info or not info['is_aws'] or not info['instance_id'] or not info['region']:
        return JsonResponse({'success': False}, status=400)

    instance_id = info['instance_id']
    region = info['region']

    if not HAS_BOTO3:
        return JsonResponse({'success': False}, status=500)

    try:
        client = _get_ec2_client(region)
        if not client:
            return JsonResponse({'success': False}, status=500)

        action_text = '시작' if action == 'start' else '종료'
        retailer_name = ', '.join(info['retailers'])

        if action == 'start':
            client.start_instances(InstanceIds=[instance_id])
        else:
            client.stop_instances(InstanceIds=[instance_id])

        logger.info(f"EC2 {action}: {instance_id} ({retailer_name}) by {request.user.username}")
        return JsonResponse({'success': True, 'message': f'{retailer_name} {action_text} 요청 완료'})

    except Exception as e:
        logger.error(f"EC2 {action} 실패 ({instance_id}): {e}")
        return JsonResponse({'success': False}, status=500)
