import logging
from datetime import datetime, timedelta
from apps.common.db import ds_connection
from apps.common.response import log_error
import boto3
from botocore.exceptions import ClientError
from config.config import S3_CONFIG, SSM_CONFIG

logger = logging.getLogger(__name__)


def get_screenshot_url(file_id):
    """
    스크린샷 이미지 URL 조회

    Args:
        file_id: ds_monitoring_file.file_id

    Returns:
        dict: success/url/file_name/file_type or error
    """
    if not file_id:
        return {'success': False, 'error': 'file_id is required'}

    try:
        with ds_connection() as (conn, cursor):
            # ds_monitoring_file에서 file_path 조회
            cursor.execute("""
                SELECT file_path, file_name, file_type
                FROM ssd_crawl_db.ds_monitoring_file
                WHERE file_id = %s AND is_del = 0
            """, (file_id,))
            row = cursor.fetchone()

        if not row:
            return {'success': False, 'error': 'File not found'}

        file_path = row[0]  # 디렉토리 경로
        file_name = row[1]  # 파일명
        file_type = row[2]

        # S3 key: 경로 + 파일명
        s3_key = file_path.rstrip('/') + '/' + file_name

        # S3 pre-signed URL 생성
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
            ExpiresIn=3600  # 1시간 유효
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
    """
    SSM을 통해 EC2 인스턴스에서 스크린샷 캡쳐 명령 실행

    Args:
        retailer: 리테일러명
        crawl_date: 수집 날짜 (YYYY-MM-DD)
        username: 요청 사용자명

    Returns:
        dict: success/message/command_id 등 or error with status
    """
    if not retailer or not crawl_date:
        return {'error': '리테일러와 날짜가 필요합니다.', 'status': 400}

    # DB에서 해당 리테일러의 instance_id, instance_region, retailer_id 조회
    try:
        with ds_connection() as (conn, cursor):
            cursor.execute("""
                SELECT retailer_id, instance_id, instance_region, mall_name FROM ssd_crawl_db.ds_monitoring_targets
                WHERE retailer = %s AND is_active = 1
            """, (retailer,))
            row = cursor.fetchone()

            if not row:
                return {'error': '해당 리테일러를 찾을 수 없습니다.', 'status': 404}

            retailer_id = row[0]
            instance_id = row[1]
            instance_region = row[2] or SSM_CONFIG['region']  # NULL이면 기본값 사용
            mall_name = row[3]

            if not instance_id:
                return {'error': '이 리테일러는 스크린샷 캡쳐를 지원하지 않습니다.', 'status': 400}

            # 30분 넘은 running → failed 자동 정리 (비정상 종료 안전장치)
            cursor.execute("""
                UPDATE ssd_crawl_db.ds_monitoring_capture_log
                SET status = 'failed'
                WHERE retailer_id = %s AND crawl_date = %s AND status = 'running'
                AND triggered_at < %s
            """, (retailer_id, crawl_date, datetime.now() - timedelta(minutes=30)))
            if cursor.rowcount > 0:
                conn.commit()

            # running 기록 확인 (중복 실행 방지)
            cursor.execute("""
                SELECT id, triggered_at FROM ssd_crawl_db.ds_monitoring_capture_log
                WHERE retailer_id = %s AND crawl_date = %s AND status = 'running'
                ORDER BY triggered_at DESC LIMIT 1
            """, (retailer_id, crawl_date))
            running_row = cursor.fetchone()

            if running_row:
                return {'error': '이미 캡쳐가 진행 중입니다.', 'status': 409}

    except Exception as e:
        return {'error': log_error(e), 'status': 500}

    # 리테일러명 변환 (소문자)
    retailer_key = retailer.lower()
    created_id = username

    # SSM 명령 실행 (Task Scheduler 방식)
    try:
        ssm_client = boto3.client(
            'ssm',
            region_name=instance_region,
            aws_access_key_id=SSM_CONFIG['access_key'],
            aws_secret_access_key=SSM_CONFIG['secret_key']
        )

        # Task Scheduler 방식: 파라미터 파일 생성 후 task 실행
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
            Parameters={
                'commands': commands
            },
            TimeoutSeconds=60
        )

        command_id = response['Command']['CommandId']

        # 캡쳐 로그 INSERT
        try:
            with ds_connection() as (conn2, cursor2):
                cursor2.execute("""
                    INSERT INTO ssd_crawl_db.ds_monitoring_capture_log
                    (retailer_id, crawl_date, triggered_at, triggered_id, status)
                    VALUES (%s, %s, %s, %s, 'running')
                """, (retailer_id, crawl_date, datetime.now(), created_id))
                conn2.commit()
        except Exception:
            pass  # 로그 INSERT 실패해도 캡쳐는 진행

        return {
            'success': True,
            'message': f'스크린샷 캡쳐 작업이 트리거되었습니다.',
            'command_id': command_id,
            'instance_id': instance_id,
            'retailer': retailer,
            'crawl_date': crawl_date,
            'task_name': task_name
        }

    except Exception as e:
        return {'error': log_error(e), 'status': 500}


def get_screenshot_status(retailer, crawl_date):
    """
    리테일러별 스크린샷 캡쳐 상태 조회

    Args:
        retailer: 리테일러명
        crawl_date: 수집 날짜 (YYYY-MM-DD)

    Returns:
        dict: retailer/total/captured/remaining/completed/is_running/triggered_at or error with status
    """
    if not retailer or not crawl_date:
        return {'error': '리테일러와 날짜가 필요합니다.', 'status': 400}

    try:
        with ds_connection() as (conn, cursor):
            # 스크린샷 캡쳐 현황
            cursor.execute("""
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN a.screenshot_id IS NOT NULL THEN 1 ELSE 0 END) as captured
                FROM ssd_crawl_db.ds_monitoring_report_anomaly a
                JOIN ssd_crawl_db.ds_monitoring_targets t ON a.retailer_id = t.retailer_id
                WHERE LOWER(t.retailer) = LOWER(%s) AND a.crawl_date = %s AND a.is_del = 0
            """, (retailer, crawl_date))

            row = cursor.fetchone()
            total = row[0] or 0
            captured = row[1] or 0
            completed = total > 0 and total == captured

            # 캡쳐 로그 처리
            is_running = False
            triggered_at = None

            # running 로그 확인
            cursor.execute("""
                SELECT cl.id, cl.triggered_at
                FROM ssd_crawl_db.ds_monitoring_capture_log cl
                JOIN ssd_crawl_db.ds_monitoring_targets t ON cl.retailer_id = t.retailer_id
                WHERE LOWER(t.retailer) = LOWER(%s) AND cl.crawl_date = %s AND cl.status = 'running'
                ORDER BY cl.triggered_at DESC LIMIT 1
            """, (retailer, crawl_date))
            log_row = cursor.fetchone()

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
    """
    스크린샷 삭제 (anomaly screenshot_id NULL + file soft delete + S3 삭제)

    Args:
        anomaly_ids: 삭제 대상 anomaly ID 목록

    Returns:
        dict: success/deleted_count or error
    """
    if not anomaly_ids:
        return {'success': False, 'error': 'anomaly_ids가 필요합니다.'}

    try:
        with ds_connection() as (conn, cursor):
            # 1. anomaly에서 screenshot_id 목록 조회
            placeholders = ','.join(['%s'] * len(anomaly_ids))
            cursor.execute(f"""
                SELECT id, screenshot_id FROM ssd_crawl_db.ds_monitoring_report_anomaly
                WHERE id IN ({placeholders}) AND screenshot_id IS NOT NULL AND is_del = 0
            """, anomaly_ids)
            anomaly_rows = cursor.fetchall()

            if not anomaly_rows:
                return {'success': False, 'error': '삭제할 스크린샷이 없습니다.'}

            screenshot_ids = [row[1] for row in anomaly_rows]
            target_anomaly_ids = [row[0] for row in anomaly_rows]

            # 2. file 테이블에서 파일 정보 조회
            file_placeholders = ','.join(['%s'] * len(screenshot_ids))
            cursor.execute(f"""
                SELECT file_id, file_path, file_name FROM ssd_crawl_db.ds_monitoring_file
                WHERE file_id IN ({file_placeholders}) AND is_del = 0
            """, screenshot_ids)
            file_rows = cursor.fetchall()

            # 3. S3 파일 삭제
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

            # 4. file 테이블 soft delete
            cursor.execute(f"""
                UPDATE ssd_crawl_db.ds_monitoring_file
                SET is_del = 1
                WHERE file_id IN ({file_placeholders})
            """, screenshot_ids)

            # 5. anomaly 테이블 screenshot_id = NULL
            anomaly_placeholders = ','.join(['%s'] * len(target_anomaly_ids))
            cursor.execute(f"""
                UPDATE ssd_crawl_db.ds_monitoring_report_anomaly
                SET screenshot_id = NULL
                WHERE id IN ({anomaly_placeholders})
            """, target_anomaly_ids)

            conn.commit()

            return {'success': True, 'deleted_count': len(target_anomaly_ids)}

    except Exception as e:
        return {'success': False, 'error': log_error(e)}


def upload_screenshot(file_obj, anomaly_id, username):
    """
    스크린샷 수동 업로드 (파일 → S3 업로드 → DB 등록 → anomaly 연결)

    Args:
        file_obj: 업로드된 파일 객체 (request.FILES에서 추출)
        anomaly_id: 이상치 ID (int)
        username: 요청 사용자명

    Returns:
        dict: success/file_id or error
    """
    if not file_obj or not anomaly_id:
        return {'success': False, 'error': '파일과 anomaly_id가 필요합니다.'}

    # 파일 검증
    allowed_types = ('image/png', 'image/jpeg')
    if file_obj.content_type not in allowed_types:
        return {'success': False, 'error': 'PNG 또는 JPG 파일만 업로드할 수 있습니다.'}

    max_size = 10 * 1024 * 1024  # 10MB
    if file_obj.size > max_size:
        return {'success': False, 'error': '파일 크기가 10MB를 초과합니다.'}

    anomaly_id = int(anomaly_id)

    try:
        with ds_connection() as (conn, cursor):
            # anomaly 조회 → retailer, crawl_date, retailersku 추출
            cursor.execute("""
                SELECT a.id, t.retailer, a.crawl_date, a.retailersku
                FROM ssd_crawl_db.ds_monitoring_report_anomaly a
                LEFT JOIN ssd_crawl_db.ds_monitoring_targets t ON a.retailer_id = t.retailer_id
                WHERE a.id = %s AND a.is_del = 0
            """, (anomaly_id,))
            row = cursor.fetchone()

            if not row:
                return {'success': False, 'error': '해당 이상치를 찾을 수 없습니다.'}

            retailer = row[1]
            crawl_date = row[2]  # date 객체
            retailersku = row[3]
            if isinstance(crawl_date, str):
                crawl_date = datetime.strptime(crawl_date, '%Y-%m-%d').date()

            # S3 키 생성 (캡쳐 프로그램과 동일 패턴: {retailer}_{retailersku}_{timestamp}.png)
            # 캡쳐 프로그램은 소문자 retailer를 사용하므로 동일하게 소문자 변환
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

            # S3 업로드
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

            # ds_monitoring_file INSERT
            created_id = username
            cursor.execute("""
                INSERT INTO ssd_crawl_db.ds_monitoring_file
                (file_name, file_path, file_size, file_type, is_del, created_at, created_id)
                VALUES (%s, %s, %s, %s, 0, %s, %s)
            """, (file_name, file_path, len(file_bytes), file_obj.content_type, now, created_id))
            file_id = cursor.lastrowid

            # anomaly.screenshot_id 업데이트
            cursor.execute("""
                UPDATE ssd_crawl_db.ds_monitoring_report_anomaly
                SET screenshot_id = %s
                WHERE id = %s
            """, (file_id, anomaly_id))

            conn.commit()

            return {'success': True, 'file_id': file_id}

    except ClientError as e:
        return {'success': False, 'error': log_error(e, 's3')}
    except Exception as e:
        return {'success': False, 'error': log_error(e)}
