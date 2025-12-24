from django.apps import AppConfig


class Layer1Config(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.layer1'
    verbose_name = 'Layer 1: 기본 통계 검수'
