"""
DS Layer 1 — 크롤러 재실행 API
"""

from django.http import JsonResponse
from datetime import datetime
from apps.common.db import get_ds_connection
from apps.common.response import safe_error
from config.config import SSM_CONFIG
import json
import boto3
import pytz


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

    # DB에서 해당 리테일러의 id, instance_id, instance_region 조회
    try:
        conn = get_ds_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT retailer_id, instance_id, instance_region, schedule_name, region_timezone FROM ssd_crawl_db.ds_monitoring_targets
            WHERE retailer = %s AND is_active = 1
        """, (retailer,))
        row = cursor.fetchone()

        if not row:
            cursor.close()
            conn.close()
            return JsonResponse({'error': '해당 리테일러를 찾을 수 없습니다.'}, status=404)

        retailer_id = row[0]
        instance_id = row[1]
        instance_region = row[2] or SSM_CONFIG['region']
        schedule_name = row[3]
        region_timezone = row[4]

        if not instance_id:
            cursor.close()
            conn.close()
            return JsonResponse({'error': '이 리테일러는 instance_id가 없어 재실행할 수 없습니다.'}, status=400)

        if not schedule_name:
            cursor.close()
            conn.close()
            return JsonResponse({'error': '이 리테일러는 schedule_name이 등록되지 않았습니다.'}, status=400)

    except Exception as e:
        return safe_error(e, 'db')

    # SSM 명령 실행 (Task Scheduler 방식)
    try:
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

        command_id = response['Command']['CommandId']

    except Exception as e:
        cursor.close()
        conn.close()
        return safe_error(e)

    now = datetime.now()

    # 재실행 로그 저장 & 배치 자동 생성
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
        batch_memo = f'재실행 ({request.user.username})'
        cursor.execute("""
            INSERT INTO ssd_crawl_db.ds_collection_batch_log
            (date, retailer, start_time, memo)
            VALUES (%s, %s, %s, %s)
        """, (crawl_date, retailer, batch_start_time, batch_memo))

        conn.commit()
    except Exception as e:
        return safe_error(e, 'save')
    finally:
        cursor.close()
        conn.close()

    return JsonResponse({
        'success': True,
        'message': f'{retailer} 크롤러 재실행이 요청되었습니다.',
        'command_id': command_id,
        'instance_id': instance_id,
        'retailer': retailer,
        'crawl_date': crawl_date,
        'schedule_name': schedule_name
    })
