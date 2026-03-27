"""
Layer 4 수집 이슈 API — 목록 조회, 저장, 삭제, 정상처리
"""

import json
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from apps.common.response import safe_error
from .services import list_issues, save_issue, delete_issue, resolve_issue


def collection_issues_list(request):
    """수집 이슈 목록 조회 (GET)"""
    date_str = request.GET.get('date')
    section = request.GET.get('section', '')

    if not date_str:
        return JsonResponse({'success': False, 'error': '날짜를 지정하세요.'}, status=400)

    try:
        return JsonResponse(list_issues(date_str, section))
    except Exception as e:
        return safe_error(e, 'collection_issues_list')


@require_POST
def collection_issue_save(request):
    """수집 이슈 저장 (INSERT or UPDATE)"""
    try:
        data = json.loads(request.body)
        crawl_date = data.get('crawl_date')
        title = data.get('title', '')

        if not crawl_date or not title:
            return JsonResponse({'success': False, 'error': '날짜와 제목은 필수입니다.'}, status=400)

        username = request.user.username if request.user.is_authenticated else ''
        result = save_issue(
            issue_id=data.get('id'),
            detail_id=data.get('detail_id'),
            crawl_date=crawl_date,
            section=data.get('section', ''),
            title=title,
            issue_date=data.get('issue_date', ''),
            symptom=data.get('symptom', ''),
            cause=data.get('cause', ''),
            action=data.get('action', ''),
            already_resolved=data.get('already_resolved', False),
            username=username,
        )
        return JsonResponse(result)
    except Exception as e:
        return safe_error(e, 'collection_issue_save')


@require_POST
def collection_issue_delete(request):
    """수집 이슈 삭제 (soft delete)"""
    try:
        data = json.loads(request.body)
        issue_id = data.get('id')
        if not issue_id:
            return JsonResponse({'success': False, 'error': 'id가 필요합니다.'}, status=400)

        username = request.user.username if request.user.is_authenticated else ''
        return JsonResponse(delete_issue(issue_id, username))
    except Exception as e:
        return safe_error(e, 'collection_issue_delete')


@require_POST
def collection_issue_resolve(request):
    """수집 이슈 정상처리"""
    try:
        data = json.loads(request.body)
        issue_id = data.get('id')
        if not issue_id:
            return JsonResponse({'success': False, 'error': 'id가 필요합니다.'}, status=400)

        username = request.user.username if request.user.is_authenticated else ''
        return JsonResponse(resolve_issue(issue_id, data.get('resolution_memo', ''), username))
    except Exception as e:
        return safe_error(e, 'collection_issue_resolve')
