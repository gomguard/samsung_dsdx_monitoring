"""
DS Document API: HTTP 요청/응답 처리
"""

import json
from django.http import JsonResponse, HttpResponseRedirect
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from apps.common.response import safe_error
from .services import (
    upload_file, get_file_proxy_url,
    get_documents_list, get_document_detail,
    create_document, update_document, delete_document,
    get_document_files, delete_file,
    create_share_token, get_share_list, revoke_share_token
)


@login_required
@require_POST
def upload(request):
    """DS 문서 이미지 업로드"""
    try:
        upload_type = int(request.POST.get('upload_type', 1))
    except (ValueError, TypeError):
        upload_type = 1

    result = upload_file(
        file=request.FILES.get('file'),
        object_document_id=request.POST.get('object_document_id', '').strip(),
        username=request.user.username,
        upload_type=upload_type
    )
    return JsonResponse(result)


@login_required
def file_proxy(request, file_name):
    """DS 문서 이미지 프록시 - S3 pre-signed URL로 리다이렉트"""
    result = get_file_proxy_url(file_name)
    if result.get('success'):
        return HttpResponseRedirect(result['url'])
    return JsonResponse(result, status=result.get('status', 500))


@login_required
def documents_list(request):
    """DS 문서 목록 조회 API"""
    result = get_documents_list(
        category_id=request.GET.get('category_id', ''),
        search_field=request.GET.get('search_field', ''),
        search_text=request.GET.get('search_text', ''),
        date_from=request.GET.get('date_from', '')
    )
    return JsonResponse(result)


@login_required
def document_detail(request):
    """DS 문서 상세 조회 API"""
    result = get_document_detail(request.GET.get('document_id', ''))
    return JsonResponse(result)


@login_required
@require_POST
def document_create(request):
    """DS 문서 생성 API"""
    try:
        data = json.loads(request.body)
        result = create_document(
            category_id=data.get('category_id', '').strip(),
            title=data.get('title', '').strip(),
            content=data.get('content', ''),
            object_document_id=data.get('object_document_id', '').strip(),
            crawl_date=data.get('crawl_date', '').strip() or None,
            username=request.user.username
        )
        return JsonResponse(result)
    except Exception as e:
        return safe_error(e, 'save')


@login_required
@require_POST
def document_update(request, document_id):
    """DS 문서 수정 API"""
    try:
        data = json.loads(request.body)
        result = update_document(
            document_id=document_id,
            title=data.get('title', '').strip(),
            content=data.get('content', ''),
            username=request.user.username
        )
        return JsonResponse(result)
    except Exception as e:
        return safe_error(e, 'update')


@login_required
@require_POST
def document_delete(request, document_id):
    """DS 문서 삭제 API"""
    result = delete_document(document_id=document_id, username=request.user.username)
    return JsonResponse(result)


@login_required
def document_files(request):
    """DS 문서 첨부파일 목록 조회 API"""
    result = get_document_files(request.GET.get('object_document_id', ''))
    return JsonResponse(result)


@login_required
@require_POST
def file_delete(request, file_id):
    """DS 첨부파일 개별 삭제 API"""
    result = delete_file(file_id=file_id, username=request.user.username)
    return JsonResponse(result)


@login_required
@require_POST
def share_token(request):
    """DS 문서 공유 토큰 생성 API"""
    try:
        data = json.loads(request.body)
        result = create_share_token(
            document_id=data.get('document_id', '').strip(),
            category_id=data.get('category_id', '').strip(),
            memo=data.get('memo', '').strip(),
            username=request.user.username
        )
        return JsonResponse(result)
    except Exception as e:
        return safe_error(e, 'save')


@login_required
def share_list(request):
    """DS 문서 공유 이력 조회 API"""
    result = get_share_list(request.GET.get('document_id', ''))
    return JsonResponse(result)


@login_required
@require_POST
def share_revoke(request):
    """DS 공유 토큰 차단 API"""
    try:
        data = json.loads(request.body)
        result = revoke_share_token(
            token_id=data.get('token_id', ''),
            username=request.user.username
        )
        return JsonResponse(result)
    except Exception as e:
        return safe_error(e, 'update')
