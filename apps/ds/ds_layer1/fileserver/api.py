"""
DS Layer 1 — 파일서버 API
request 파싱 + services 호출 + JsonResponse 반환
"""

from django.http import JsonResponse
from datetime import datetime, timedelta
from apps.common.response import log_error
from . import services
import json


def fileserver_stats(request):
    """파일서버 날짜별 용량 조회 API"""
    date_str = request.GET.get('date')

    if date_str:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    else:
        target_date = (datetime.now() - timedelta(days=1)).date()

    data = {
        'timestamp': datetime.now().isoformat(),
        'date': str(target_date),
        'date_folder': target_date.strftime('%Y%m%d'),
        'countries': [],
        'summary': {}
    }

    try:
        result = services.get_fileserver_stats(target_date)

        data['date_folder'] = result['date_folder']
        data['countries'] = result['countries']
        data['summary'] = result['summary']

    except Exception as e:
        data['error'] = log_error(e)
        data['summary'] = {
            'total_countries': 0,
            'total_files': 0,
            'total_size': 0
        }

    return JsonResponse(data)


def fileserver_browse(request):
    """파일서버 탐색 API"""
    date_str = request.GET.get('date')
    country = request.GET.get('country', '').strip()

    # country 없으면 국가 목록만 반환
    if not country:
        try:
            countries = services.get_country_list()
            return JsonResponse({'countries': countries})
        except Exception as e:
            return JsonResponse({'error': log_error(e)}, status=500)

    # Path Traversal 방지
    err = services.validate_path_segment(country, '국가 코드')
    if err:
        return JsonResponse({'error': err}, status=400)

    # 날짜 파싱
    today = datetime.now().date()
    if date_str:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        if target_date > today:
            target_date = today
    else:
        target_date = (datetime.now() - timedelta(days=1)).date()

    try:
        result = services.browse_country_files(country, target_date)
        return JsonResponse(result)
    except FileNotFoundError as e:
        return JsonResponse({'error': str(e)}, status=404)
    except Exception as e:
        return JsonResponse({'error': log_error(e)}, status=500)


def fileserver_move(request):
    """파일서버 파일 이동 API"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST 요청만 허용됩니다.'}, status=405)

    try:
        body = json.loads(request.body)
    except Exception:
        return JsonResponse({'error': '잘못된 요청 형식입니다.'}, status=400)

    country = body.get('country', '').strip()
    date_folder = body.get('date_folder', '').strip()
    files = body.get('files', [])

    if not country or not date_folder or not files:
        return JsonResponse({'error': 'country, date_folder, files가 필요합니다.'}, status=400)

    # Path Traversal 방지
    for label, val in [('국가 코드', country), ('날짜 폴더', date_folder)]:
        err = services.validate_path_segment(val, label)
        if err:
            return JsonResponse({'error': err}, status=400)
    for filename in files:
        err = services.validate_path_segment(filename, '파일명')
        if err:
            return JsonResponse({'error': err}, status=400)

    try:
        result = services.move_files_to_backup(country, date_folder, files)
        return JsonResponse(result)
    except Exception as e:
        return JsonResponse({'error': log_error(e)}, status=500)
