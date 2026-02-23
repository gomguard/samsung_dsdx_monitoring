from django.apps import AppConfig


class Layer3Config(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.dx.dx_layer3'
    verbose_name = 'Layer 3: 이상치/특수 케이스 검수'
