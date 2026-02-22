"""
공통 API 에러 응답 함수

사용법:
    from apps.common.response import safe_error, log_error

    # return용 (JsonResponse 반환)
    except Exception as e:
        return safe_error(e)                         # 기본 메시지, 500
        return safe_error(e, 'save')                 # '저장 중 오류가 발생했습니다.', 500
        return safe_error(e, 'save', 200)            # '저장 중 오류가 발생했습니다.', 200
        return safe_error(e, success=False)           # 추가 필드 포함
        return safe_error(e, 'db', anomalies=[])     # ERR 키 + 추가 필드

    # data dict용 (문자열만 반환)
    except Exception as e:
        data['error'] = log_error(e)                 # 기본 메시지
        data['error'] = log_error(e, 'db')           # 'DB 조회 중 오류가 발생했습니다.'
"""
import inspect
import traceback
from django.http import JsonResponse


# 에러 메시지 상수
ERR = {
    'default': '처리 중 오류가 발생했습니다.',
    'db':      'DB 조회 중 오류가 발생했습니다.',
    'save':    '저장 중 오류가 발생했습니다.',
    'update':  '수정 중 오류가 발생했습니다.',
    'delete':  '삭제 중 오류가 발생했습니다.',
    'upload':  '파일 업로드 중 오류가 발생했습니다.',
    'backup':  '백업 중 오류가 발생했습니다.',
    'param':   '잘못된 요청 파라미터입니다.',
    's3':      '파일 처리 중 오류가 발생했습니다.',
}


def safe_error(e, msg='default', status=500, **extra):
    """
    공통 에러 응답 (return용)
    - 호출한 함수명 자동 감지 → 서버 콘솔 출력
    - 제네릭 메시지만 클라이언트에 반환

    Args:
        e: Exception 객체
        msg: ERR 키 또는 직접 문자열
        status: HTTP 상태 코드 (기본 500)
        **extra: 추가 JSON 필드 (success=False, anomalies=[] 등)

    Returns:
        JsonResponse
    """
    caller = inspect.stack()[1].function
    print(f'[ERROR] {caller}: {e}')
    traceback.print_exc()
    message = ERR.get(msg, msg)
    return JsonResponse({'error': message, **extra}, status=status)


def log_error(e, msg='default'):
    """
    에러 로깅 + 제네릭 메시지 반환 (data dict용)
    - 호출한 함수명 자동 감지 → 서버 콘솔 출력
    - 제네릭 메시지 문자열 반환

    Args:
        e: Exception 객체
        msg: ERR 키 또는 직접 문자열

    Returns:
        str: 클라이언트에 보여줄 에러 메시지
    """
    caller = inspect.stack()[1].function
    print(f'[ERROR] {caller}: {e}')
    traceback.print_exc()
    return ERR.get(msg, msg)
