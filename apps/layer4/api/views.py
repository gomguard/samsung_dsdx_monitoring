from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
import json


def layer4_status(request):
    """Layer4 저장/분석 현황 조회"""
    date = request.GET.get('date')

    # TODO: 실제 DB 조회 로직 구현
    # SuspiciousCase.objects.filter(collection_date=date).count()

    return JsonResponse({
        'date': date,
        'saved_count': 0,
        'analyzed_count': 0,
        'pending_count': 0
    })


@csrf_exempt
@require_http_methods(["POST"])
def save_suspicious(request):
    """Layer3에서 발견된 의심 케이스를 DB에 저장"""
    try:
        data = json.loads(request.body)
        date = data.get('date')
        product_line = data.get('product_line')

        # TODO: 실제 저장 로직 구현
        # 1. Layer3 cross-field 검증 쿼리 실행
        # 2. 결과를 SuspiciousCase 테이블에 저장

        saved_count = 0  # 실제 저장된 건수

        return JsonResponse({
            'success': True,
            'saved_count': saved_count,
            'date': date,
            'product_line': product_line
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def start_analysis(request):
    """저장된 의심 케이스에 대해 LLM 분석 시작"""
    try:
        data = json.loads(request.body)
        date = data.get('date')

        # TODO: 실제 LLM 분석 로직 구현
        # 1. analyzed_at IS NULL인 케이스 조회
        # 2. LLM API 호출
        # 3. 결과 저장

        analyzed_count = 0

        return JsonResponse({
            'success': True,
            'analyzed_count': analyzed_count,
            'date': date
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


def get_cases(request):
    """저장된 케이스 목록 조회"""
    date = request.GET.get('date')
    status = request.GET.get('status', 'all')  # all, pending, analyzed

    # TODO: 실제 DB 조회 로직 구현

    return JsonResponse({
        'date': date,
        'cases': [],
        'total': 0
    })
