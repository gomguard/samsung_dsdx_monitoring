"""
공통 요청 파라미터 파싱 함수

사용법:
    from apps.common.params import parse_date

    # 빈 값이면 어제 날짜 (기본)
    target_date = parse_date(request.GET.get('date'))

    # 빈 값이면 오늘 날짜
    target_date = parse_date(request.GET.get('date'), default='today')

    # 빈 값이면 None (날짜 필수)
    target_date = parse_date(request.GET.get('date'), default=None)

    # 잘못된 형식이면 None 반환 → 400 응답 처리
    if target_date is None:
        return JsonResponse({'error': '날짜 형식이 올바르지 않습니다.'}, status=400)
"""
from datetime import datetime, timedelta


def parse_date(date_str, default='yesterday'):
    """date 파라미터 파싱 (YYYY-MM-DD)

    Args:
        date_str: 'YYYY-MM-DD' 형식 문자열 (None 또는 빈 문자열 가능)
        default: 빈 값일 때 기본값
            - 'yesterday': 어제 날짜 (기본)
            - 'today': 오늘 날짜
            - None: 기본값 없음 (None 반환)

    Returns:
        date 객체 또는 None (잘못된 형식이거나 default=None일 때 빈 값)
    """
    if not date_str:
        if default == 'yesterday':
            return (datetime.now() - timedelta(days=1)).date()
        elif default == 'today':
            return datetime.now().date()
        return None
    try:
        return datetime.strptime(date_str, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return None
