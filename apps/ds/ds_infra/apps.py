from django.apps import AppConfig


class InfraConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.ds.ds_infra'
    verbose_name = '인프라 모니터링'
