"""
DS Layer 1 — 크롤러 재실행 서비스
DB 조회 + SSM 실행 + 로그 저장 (순수 비즈니스 로직)
"""

from datetime import datetime
from apps.common.db import get_ds_connection
from config.config import SSM_CONFIG
import boto3
import pytz


def get_retailer_info(retailer):
    """DB에서 해당 리테일러의 정보 조회. 없으면 None 반환"""
    conn = get_ds_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT retailer_id, instance_id, instance_region, schedule_name, region_timezone
            FROM ssd_crawl_db.ds_monitoring_targets
            WHERE retailer = %s AND is_active = 1
        """, (retailer,))
        row = cursor.fetchone()

        if not row:
            return None

        return {
            'retailer_id': row[0],
            'instance_id': row[1],
            'instance_region': row[2] or SSM_CONFIG['region'],
            'schedule_name': row[3],
            'region_timezone': row[4]
        }
    finally:
        cursor.close()
        conn.close()


def execute_ssm_command(instance_id, instance_region, schedule_name, retailer, crawl_date):
    """SSM 명령 실행 (Task Scheduler 방식). command_id 반환"""
    ssm_client = boto3.client(
        'ssm',
        region_name=instance_region,
        aws_access_key_id=SSM_CONFIG['access_key'],
        aws_secret_access_key=SSM_CONFIG['secret_key']
    )

    commands = [
        f'schtasks /run /tn "{schedule_name}"',
        f'Write-Output "Task {schedule_name} triggered for {retailer} ({crawl_date})"'
    ]

    response = ssm_client.send_command(
        InstanceIds=[instance_id],
        DocumentName='AWS-RunPowerShellScript',
        Parameters={
            'commands': commands
        },
        TimeoutSeconds=60
    )

    return response['Command']['CommandId']


def save_rerun_log(retailer_id, retailer, crawl_date, schedule_name, created_id, instance_id, command_id, region_timezone, username):
    """재실행 로그 저장 & 배치 자동 생성"""
    conn = get_ds_connection()
    cursor = conn.cursor()
    now = datetime.now()

    try:
        # 재실행 로그 저장
        cursor.execute("""
            INSERT INTO ssd_crawl_db.ds_monitoring_crawler_rerun_log
            (retailer_id, crawl_date, schedule_name, created_id, instance_id, command_id, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (retailer_id, crawl_date, schedule_name, created_id, instance_id, command_id, now))

        # 배치 로그 자동 생성 (start_time = 리테일러 타임존 기준)
        if region_timezone:
            tz = pytz.timezone(region_timezone)
            local_now = datetime.now(tz)
            batch_start_time = local_now.strftime('%H:%M:%S')
        else:
            batch_start_time = now.strftime('%H:%M:%S')
        batch_memo = f'재실행 ({username})'
        cursor.execute("""
            INSERT INTO ssd_crawl_db.ds_collection_batch_log
            (date, retailer, start_time, memo)
            VALUES (%s, %s, %s, %s)
        """, (crawl_date, retailer, batch_start_time, batch_memo))

        conn.commit()
    finally:
        cursor.close()
        conn.close()
