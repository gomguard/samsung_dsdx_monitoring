import boto3
from config.config import SSM_CONFIG

class SSMAdapter:
    """AWS Systems Manager (SSM) 통신을 전담하는 Adapter 클래스"""
    
    def execute_command(self, instance_id, instance_region, schedule_name, retailer, crawl_date):
        """특정 인스턴스에 schtasks 명령하달 후 command_id 반환"""
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
