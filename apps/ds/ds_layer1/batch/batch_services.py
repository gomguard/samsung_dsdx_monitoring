"""
DS Layer 1 — 배치 로그 서비스
비즈니스 로직 및 데이터 가공만 담당 (DB 쿼리 없음)
"""

from apps.common.targets import load_monitoring_targets_with_local_time, format_time
from . import batch_repositories


def get_batches_for_date(target_date):
    """특정 날짜의 배치 목록을 리테일러별로 그룹화하여 반환"""
    batches_by_retailer = {}

    try:
        raw_batches = batch_repositories.get_batches_by_date(target_date)

        for batch in raw_batches:
            retailer = batch['retailer']
            if retailer not in batches_by_retailer:
                batches_by_retailer[retailer] = []

            batches_by_retailer[retailer].append({
                'id': batch['id'],
                'start_time': format_time(batch['start_time']) if batch.get('start_time') else '00:00',
                'memo': batch['memo']
            })
    except Exception as e:
        print(f"Error loading batches: {e}")

    return batches_by_retailer


def get_batch_list(target_date):
    """해당 날짜의 배치 로그 목록 조회"""
    raw_batches = batch_repositories.get_batches_by_date(target_date)

    batches = []
    for batch in raw_batches:
        batches.append({
            'id': batch['id'],
            'date': str(batch['date']),
            'retailer': batch['retailer'],
            'start_time': format_time(batch['start_time']) if batch.get('start_time') else None,
            'memo': batch['memo'],
            'created_at': batch['created_at'].isoformat() if batch.get('created_at') else None
        })

    return batches


def init_batches(target_date):
    """해당 날짜에 기본 배치 생성. 이미 존재하면 0 반환"""
    count = batch_repositories.count_batches_by_date(target_date)

    if count > 0:
        return 0

    targets = load_monitoring_targets_with_local_time()
    
    batch_data_list = []
    for table_name, retailer, region, korea_time, local_time, country, mall_name in targets:
        batch_data_list.append((target_date, retailer, local_time + ':00', None))

    created_count = batch_repositories.insert_batches_bulk(batch_data_list)
    return created_count


def create_batch(date_str, retailer, start_time, memo):
    """배치 로그 추가. 새로 생성된 ID 반환"""
    return batch_repositories.insert_batch(date_str, retailer, start_time, memo)


def update_batch(batch_id, start_time, memo):
    """배치 로그 수정. 영향받은 행 수 반환"""
    updates = {}
    
    if start_time is not None:
        updates['start_time'] = start_time

    if memo is not None:
        updates['memo'] = memo

    if not updates:
        return -1  # 수정할 필드 없음

    return batch_repositories.update_batch_dynamic(batch_id, updates)


def delete_batch(batch_id):
    """배치 로그 삭제. 영향받은 행 수 반환"""
    return batch_repositories.delete_batch(batch_id)
