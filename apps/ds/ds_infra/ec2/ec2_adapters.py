"""
인프라 모니터링: AWS EC2 통신 전담 어댑터
비즈니스 로직(서비스)에서 Boto3와 직접 결합하지 않도록 추상화합니다.
"""

import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

try:
    import boto3
    HAS_BOTO3 = True
except ImportError:
    HAS_BOTO3 = False

try:
    from config.config import SSM_CONFIG
except ImportError:
    SSM_CONFIG = {}


class EC2Adapter:
    """
    AWS EC2 인스턴스 조회 및 제어를 담당하는 Adapter 객체.
    Connection 관리를 위해 Context Manager 구조(with ~ as)를 지원합니다.
    """

    def __init__(self, region: str):
        self.region = region
        self.client = None
    
    def __enter__(self):
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def connect(self):
        """boto3 ec2 클라이언트 생성 (연결)"""
        if not HAS_BOTO3:
            return
        if not SSM_CONFIG.get('access_key') or not SSM_CONFIG.get('secret_key'):
            return
        
        try:
            self.client = boto3.client(
                'ec2',
                region_name=self.region,
                aws_access_key_id=SSM_CONFIG['access_key'],
                aws_secret_access_key=SSM_CONFIG['secret_key'],
            )
        except Exception as e:
            logger.error(f"EC2 Client 생성 실패 (region={self.region}): {e}")
            self.client = None

    def close(self):
        """boto3 client 소멸 처리 (필요시 세션 자원 안전 반환)"""
        if self.client:
            # boto3 client는 내부적으로 HTTP 커넥션 풀을 관리하며, 명시적으로 닫기 지원 시 close()
            if hasattr(self.client, 'close'):
                self.client.close()
            self.client = None

    def describe_instances(self, instance_ids: List[str]) -> Dict[str, Dict[str, Any]]:
        """해당 리전의 EC2 인스턴스 상태를 조회합니다."""
        result = {}
        if not self.client:
            for iid in instance_ids:
                result[iid] = {'state': 'unknown', 'name': ''}
            return result

        try:
            response = self.client.describe_instances(InstanceIds=instance_ids)
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
            logger.error(f"EC2 describe_instances 실패 (region={self.region}): {e}")
            for iid in instance_ids:
                if iid not in result:
                    result[iid] = {'state': 'unknown', 'name': ''}
        return result

    def start_instance(self, instance_id: str) -> bool:
        """단일 EC2 인스턴스를 시작합니다."""
        if not self.client:
            return False
        
        try:
            self.client.start_instances(InstanceIds=[instance_id])
            return True
        except Exception as e:
            logger.error(f"EC2 start_instance 실패 (instance_id={instance_id}, region={self.region}): {e}")
            return False

    def stop_instance(self, instance_id: str) -> bool:
        """단일 EC2 인스턴스를 중지합니다."""
        if not self.client:
            return False
        
        try:
            self.client.stop_instances(InstanceIds=[instance_id])
            return True
        except Exception as e:
            logger.error(f"EC2 stop_instance 실패 (instance_id={instance_id}, region={self.region}): {e}")
            return False
