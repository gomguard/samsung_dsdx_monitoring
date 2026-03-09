"""
Layer 4: 검수 확인 / 보고서 (Review & Report)

각 메뉴별 페이지 뷰는 하위 모듈로 분리됨.
이 파일은 하위호환을 위해 유지하며, 실제 뷰 함수를 re-export 합니다.
"""

from apps.dx.dx_layer4.dashboard.views import dashboard
from apps.dx.dx_layer4.check_log.views import check_log, check_log_detail
from apps.dx.dx_layer4.corrections.views import corrections
from apps.dx.dx_layer4.report.views import report

__all__ = ['dashboard', 'check_log', 'check_log_detail', 'corrections', 'report']
