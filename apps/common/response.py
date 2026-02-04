"""
공통 API 응답 함수
"""
import logging
from django.http import JsonResponse

logger = logging.getLogger(__name__)


def error_response(e, message=None, status=500):
    """
    공통 에러 응답 함수
    - traceback 자동 출력 (콘솔)
    - 일관된 JSON 응답 반환

    Args:
        e: Exception 객체
        message: 사용자에게 보여줄 에러 메시지 (없으면 예외 메시지 사용)
        status: HTTP 상태 코드 (기본 500)

    Returns:
        JsonResponse: {'error': message, 'detail': str(e)}
    """
    logger.exception(message or 'API Error')

    return JsonResponse({
        'error': message or str(e),
        'detail': str(e)
    }, status=status)
