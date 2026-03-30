import logging
from datetime import datetime, timedelta
import boto3
from botocore.exceptions import ClientError
from apps.common.response import log_error
from config.config import S3_CONFIG, SSM_CONFIG
from . import screenshot_repositories

logger = logging.getLogger(__name__)

def get_screenshot_url(file_id):
    """스크린샷 이미지 URL 조회"""
    if not file_id:
        return {'success': False, 'error': 'file_id is required'}

    try:
        row = screenshot_repositories.get_screenshot_file_info(file_id)
        if not row:
            return {'success': False, 'error': 'File not found'}

        file_path, file_name, file_type = row
        s3_key = file_path.rstrip('/') + '/' + file_name

        s3_client = boto3.client(
            's3',
            region_name=S3_CONFIG['region'],
            aws_access_key_id=S3_CONFIG['access_key'],
            aws_secret_access_key=S3_CONFIG['secret_key']
        )

        url = s3_client.generate_presigned_url(
            'get_object',
            Params={
                'Bucket': S3_CONFIG['bucket'],
                'Key': s3_key
            },
            ExpiresIn=3600
        )

        return {
            'success': True,
            'url': url,
            'file_name': file_name,
            'file_type': file_type
        }

    except ClientError as e:
        return {'success': False, 'error': log_error(e, 's3')}
    except Exception as e:
        return {'success': False, 'error': log_error(e)}


def trigger_screenshot_capture(retailer, crawl_date, username):
    """SSM을 통해 EC2 인스턴스에서 스크린샷 캡쳐 명령 실행"""
    if not retailer or not crawl_date:
        return {'error': '리테일러와 날짜가 필요합니다.', 'status': 400}

    try:
        row = screenshot_repositories.get_retailer_instance_info(retailer)
        if not row:
            return {'error': '해당 리테일러를 찾을 수 없습니다.', 'status': 404}

        retailer_id, instance_id, instance_region, mall_name = row
        instance_region = instance_region or SSM_CONFIG['region']

        if not instance_id:
            return {'error': '이 리테일러는 스크린샷 캡쳐를 지원하지 않습니다.', 'status': 400}

        screenshot_repositories.expire_running_captures(retailer_id, crawl_date, 30)

        running_row = screenshot_repositories.get_latest_running_capture(retailer_id, crawl_date)
        if running_row:
            return {'error': '이미 캡쳐가 진행 중입니다.', 'status': 409}

    except Exception as e:
        return {'error': log_error(e), 'status': 500}

    retailer_key = retailer.lower()
    created_id = username

    try:
        ssm_client = boto3.client(
            'ssm',
            region_name=instance_region,
            aws_access_key_id=SSM_CONFIG['access_key'],
            aws_secret_access_key=SSM_CONFIG['secret_key']
        )

        task_name = 'capture_error'
        param_file = 'C:\\samsung_ds_retail_com\\monitoring\\capture_params.json'
        param_json = f'{{"retailer": "{retailer_key}", "crawl_date": "{crawl_date}", "created_id": "{created_id}"}}'

        commands = [
            f'Set-Content -Path "{param_file}" -Value \'{param_json}\' -Encoding UTF8',
            f'schtasks /run /tn "{task_name}"',
            f'Write-Output "Task {task_name} triggered with params: {param_json}"'
        ]

        response = ssm_client.send_command(
            InstanceIds=[instance_id],
            DocumentName='AWS-RunPowerShellScript',
            Parameters={'commands': commands},
            TimeoutSeconds=60
        )

        command_id = response['Command']['CommandId']

        try:
            screenshot_repositories.insert_capture_log(retailer_id, crawl_date, created_id)
        except Exception:
            pass

        return {
            'success': True,
            'message': '스크린샷 캡쳐 작업이 트리거되었습니다.',
            'command_id': command_id,
            'instance_id': instance_id,
            'retailer': retailer,
            'crawl_date': crawl_date,
            'task_name': task_name
        }

    except Exception as e:
        return {'error': log_error(e), 'status': 500}


def get_screenshot_status(retailer, crawl_date):
    """리테일러별 스크린샷 캡쳐 상태 조회"""
    if not retailer or not crawl_date:
        return {'error': '리테일러와 날짜가 필요합니다.', 'status': 400}

    try:
        total_row, log_row = screenshot_repositories.get_screenshot_status_summary(retailer, crawl_date)

        total = total_row[0] or 0 if total_row else 0
        captured = total_row[1] or 0 if total_row else 0
        completed = total > 0 and total == captured

        is_running = False
        triggered_at = None

        if log_row:
            is_running = True
            triggered_at = log_row[1].strftime('%Y-%m-%d %H:%M:%S') if log_row[1] else None

        return {
            'retailer': retailer,
            'total': total,
            'captured': captured,
            'remaining': total - captured,
            'completed': completed,
            'is_running': is_running,
            'triggered_at': triggered_at
        }
    except Exception as e:
        return {'error': log_error(e, 'db'), 'status': 500}


def delete_screenshots(anomaly_ids):
    """스크린샷 삭제 (파일 soft delete + S3 삭제 + 참조 NULL)"""
    if not anomaly_ids:
        return {'success': False, 'error': 'anomaly_ids가 필요합니다.'}

    try:
        result = screenshot_repositories.soft_delete_screenshots(anomaly_ids)
        if not result:
            return {'success': False, 'error': '삭제할 스크린샷이 없습니다.'}

        file_rows, deleted_count = result

        if file_rows:
            try:
                s3_client = boto3.client(
                    's3',
                    region_name=S3_CONFIG['region'],
                    aws_access_key_id=S3_CONFIG['access_key'],
                    aws_secret_access_key=S3_CONFIG['secret_key']
                )
                for f in file_rows:
                    s3_key = f'{f[1].rstrip("/")}/{f[2]}'
                    s3_client.delete_object(Bucket=S3_CONFIG['bucket'], Key=s3_key)
            except Exception:
                pass

        return {'success': True, 'deleted_count': deleted_count}

    except Exception as e:
        return {'success': False, 'error': log_error(e)}


def upload_screenshot(file_obj, anomaly_id, username):
    """스크린샷 수동 업로드 (S3 업로드 → DB 메타데이터 등록)"""
    if not file_obj or not anomaly_id:
        return {'success': False, 'error': '파일과 anomaly_id가 필요합니다.'}

    allowed_types = ('image/png', 'image/jpeg')
    if file_obj.content_type not in allowed_types:
        return {'success': False, 'error': 'PNG 또는 JPG 파일만 업로드할 수 있습니다.'}

    max_size = 10 * 1024 * 1024
    if file_obj.size > max_size:
        return {'success': False, 'error': '파일 크기가 10MB를 초과합니다.'}

    anomaly_id = int(anomaly_id)

    try:
        row = screenshot_repositories.get_anomaly_for_upload(anomaly_id)
        if not row:
            return {'success': False, 'error': '해당 이상치를 찾을 수 없습니다.'}

        _, retailer, crawl_date, retailersku = row
        if isinstance(crawl_date, str):
            crawl_date = datetime.strptime(crawl_date, '%Y-%m-%d').date()

        retailer_lower = retailer.lower()
        now = datetime.now()
        year = crawl_date.strftime('%Y')
        year_month = crawl_date.strftime('%Y%m')
        year_month_day = crawl_date.strftime('%Y%m%d')
        creation_timestamp = now.strftime('%Y%m%d%H%M%S')

        if retailersku:
            file_name = f"{retailer_lower}_{retailersku}_{creation_timestamp}.png"
        else:
            file_name = f"{retailer_lower}_{creation_timestamp}.png"

        file_path = f"{year}/{year_month}/{year_month_day}/{retailer_lower}/"
        s3_key = f"{file_path}{file_name}"

        file_bytes = file_obj.read()
        s3_client = boto3.client(
            's3',
            region_name=S3_CONFIG['region'],
            aws_access_key_id=S3_CONFIG['access_key'],
            aws_secret_access_key=S3_CONFIG['secret_key']
        )
        s3_client.put_object(
            Bucket=S3_CONFIG['bucket'],
            Key=s3_key,
            Body=file_bytes,
            ContentType=file_obj.content_type
        )

        file_id = screenshot_repositories.insert_uploaded_file(
            file_name, file_path, len(file_bytes), file_obj.content_type, username, anomaly_id
        )

        return {'success': True, 'file_id': file_id}

    except ClientError as e:
        return {'success': False, 'error': log_error(e, 's3')}
    except Exception as e:
        return {'success': False, 'error': log_error(e)}
