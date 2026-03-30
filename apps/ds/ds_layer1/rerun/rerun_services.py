"""
DS Layer 1 — 크롤러 재실행 서비스
DB 및 SSM 외부 통신을 배제한 순수 비즈니스 로직
"""

from datetime import datetime
import pytz
from config.config import SSM_CONFIG
from .rerun_repositories import get_retailer_info_db, save_rerun_log_db
from .rerun_adapters import SSMAdapter


def get_retailer_info(retailer):
    """DB에서 해당 리테일러의 인스턴스 정보 연산 후 반환"""
    row = get_retailer_info_db(retailer)
    if not row:
        return None

    return {
        'retailer_id': row['retailer_id'],
        'instance_id': row['instance_id'],
        'instance_region': row['instance_region'] or SSM_CONFIG['region'],
        'schedule_name': row['schedule_name'],
        'region_timezone': row['region_timezone']
    }


def execute_ssm_command(instance_id, instance_region, schedule_name, retailer, crawl_date):
    """어댑터를 이용해 SSM 명령 하달 후 command_id 획득"""
    adapter = SSMAdapter()
    return adapter.execute_command(instance_id, instance_region, schedule_name, retailer, crawl_date)


def save_rerun_log(retailer_id, retailer, crawl_date, schedule_name, created_id, instance_id, command_id, region_timezone, username):
    """배치 시작 시간을 계산(비즈니스 로직) 후 레포지토리에 저장 의뢰"""
    now = datetime.now()
    
    # 시간 타임존에 기반한 계산 (순수 비즈니스 로직)
    if region_timezone:
        tz = pytz.timezone(region_timezone)
        local_now = datetime.now(tz)
        batch_start_time = local_now.strftime('%H:%M:%S')
    else:
        batch_start_time = now.strftime('%H:%M:%S')
        
    batch_memo = f'재실행 ({username})'

    save_rerun_log_db(
        retailer_id=retailer_id,
        retailer=retailer,
        crawl_date=crawl_date,
        schedule_name=schedule_name,
        created_id=created_id,
        instance_id=instance_id,
        command_id=command_id,
        batch_start_time=batch_start_time,
        batch_memo=batch_memo,
        now=now
    )
