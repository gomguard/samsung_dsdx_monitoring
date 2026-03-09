"""
Layer 3: 이상치/특수 케이스 검수 (Outlier & Anomaly Detection)

각 메뉴별 페이지 뷰는 하위 모듈로 분리됨.
이 파일은 하위호환을 위해 유지하며, 실제 뷰 함수를 re-export 합니다.
"""

from apps.dx.dx_layer3.dashboard.views import dashboard
from apps.dx.dx_layer3.time_series.views import time_series
from apps.dx.dx_layer3.cross_field.views import cross_field
from apps.dx.dx_layer3.category_spec.views import category_spec
from apps.dx.dx_layer3.field_missing.views import field_missing

__all__ = ['dashboard', 'time_series', 'cross_field', 'category_spec', 'field_missing']
