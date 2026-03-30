"""
인프라 모니터링: 순수 비즈니스 로직 및 스레드 병렬 계산
어댑터(Adapter)를 호출하여 Boto3 라이브러리와 통신을 격리합니다.
"""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from apps.common.targets import load_ec2_instances
from .infra_adapters import EC2Adapter

logger = logging.getLogger(__name__)


def get_ec2_status():
    """EC2 인스턴스 상태 조회 (병렬 처리 + 비즈니스 응답 구성)"""
    instances = load_ec2_instances()

    if not instances:
        return []

    # 리전별 그룹핑
    region_map = {}
    for key, info in instances.items():
        if info['is_aws'] and info['instance_id'] and info['region']:
            region = info['region']
            if region not in region_map:
                region_map[region] = []
            region_map[region].append(info['instance_id'])

    state_map = {}

    def fetch_region(region, instance_ids):
        # Adapter 계층 호출로 Boto3 캡슐화 (with context manager)
        with EC2Adapter(region) as adapter:
            return adapter.describe_instances(instance_ids)

    with ThreadPoolExecutor(max_workers=len(region_map) or 1) as executor:
        futures = {
            executor.submit(fetch_region, region, ids): region
            for region, ids in region_map.items()
        }
        for future in as_completed(futures):
            state_map.update(future.result())

    # 응답 구성
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

    return result


def perform_ec2_action(key, action, username):
    """EC2 인스턴스 시작/종료 명령 판단"""
    if not key or action not in ('start', 'stop'):
        return {'success': False, 'message': 'Invalid parameter', 'status': 400}

    instances = load_ec2_instances()
    info = instances.get(key)
    if not info or not info['is_aws'] or not info['instance_id'] or not info['region']:
        return {'success': False, 'message': 'Invalid instance target', 'status': 400}

    instance_id = info['instance_id']
    region = info['region']
    retailer_name = ', '.join(info['retailers'])
    action_text = '시작' if action == 'start' else '종료'

    # Adapter 계층 호출로 Boto3 분리
    with EC2Adapter(region) as adapter:
        if action == 'start':
            success = adapter.start_instance(instance_id)
        else:
            success = adapter.stop_instance(instance_id)

    if success:
        logger.info(f"EC2 {action}: {instance_id} ({retailer_name}) by {username}")
        return {'success': True, 'message': f'{retailer_name} {action_text} 요청 완료', 'status': 200}
    else:
        return {'success': False, 'message': 'AWS 통신 실패', 'status': 500}
