from django.apps import AppConfig


class Layer4Config(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.layer4'
    verbose_name = 'Layer 4: 문맥/의미 검증'
