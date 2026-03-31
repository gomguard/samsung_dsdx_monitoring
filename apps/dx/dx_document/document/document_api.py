"""
DX Document API
문서 CRUD, 파일 업로드, 공유 토큰 관리
"""

from django.http import JsonResponse, HttpResponseRedirect
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from apps.common.response import safe_error
from apps.dx.dx_document.document.document_services import (
    get_documents_list,
    get_document_detail,
    create_document,
    update_document,
    delete_document,
    upload_file,
    get_file_proxy_url,
    delete_file,
    get_document_files,
    create_share_token,
    get_share_list,
    revoke_share_token,
)
import json


def documents_list(request):
    """문서 목록 조회 API (카테고리별)"""
    category_id = request.GET.get('category_id', '')

    if not category_id:
        return JsonResponse({'success': False, 'error': '카테고리 ID가 필요합니다.'})

    try:
        return JsonResponse(get_documents_list(category_id))
    except Exception as e:
        return safe_error(e, success=False)


def document_detail(request):
    """문서 상세 조회 API"""
    document_id = request.GET.get('document_id', '')

    if not document_id:
        return JsonResponse({'success': False, 'error': '문서 ID가 필요합니다.'})

    try:
        document = get_document_detail(document_id)
        if not document:
            return JsonResponse({'success': False, 'error': '문서를 찾을 수 없습니다.'})
        return JsonResponse({'success': True, 'document': document})
    except Exception as e:
        return safe_error(e, success=False)


@login_required
@require_POST
def document_create(request):
    """문서 생성 API (crawl_date 중복 시 업데이트)"""
    try:
        data = json.loads(request.body)
        category_id = data.get('category_id', '').strip()
        title = data.get('title', '').strip()
        content = data.get('content', '')
        object_document_id = data.get('object_document_id', '').strip()
        crawl_date = data.get('crawl_date', '').strip() or None

        if not category_id:
            return JsonResponse({'success': False, 'error': '카테고리를 선택하세요.'})
        if not title:
            return JsonResponse({'success': False, 'error': '제목을 입력하세요.'})

        result = create_document(category_id, title, content, object_document_id, crawl_date, request.user.username)
        return JsonResponse(result)
    except Exception as e:
        return safe_error(e, success=False)


@login_required
@require_POST
def document_update(request, document_id):
    """문서 수정 API"""
    try:
        data = json.loads(request.body)
        title = data.get('title', '').strip()
        content = data.get('content', '')

        if not title:
            return JsonResponse({'success': False, 'error': '제목을 입력하세요.'})

        return JsonResponse(update_document(document_id, title, content, request.user.username))
    except Exception as e:
        return safe_error(e, success=False)


@login_required
@require_POST
def document_delete(request, document_id):
    """문서 삭제 API (soft delete + 파일 정리)"""
    try:
        return JsonResponse(delete_document(document_id, request.user.username))
    except Exception as e:
        return safe_error(e, success=False)


@login_required
@require_POST
def upload(request):
    """문서 파일 업로드 API (S3)"""
    try:
        file = request.FILES.get('file')
        object_document_id = request.POST.get('object_document_id', '').strip()
        try:
            upload_type = int(request.POST.get('upload_type', 1))
        except (ValueError, TypeError):
            upload_type = 1
        if upload_type not in (1, 2):
            upload_type = 1

        if not file:
            return JsonResponse({'success': False, 'error': '파일이 없습니다.'})
        if not object_document_id:
            return JsonResponse({'success': False, 'error': 'object_document_id가 필요합니다.'})

        return JsonResponse(upload_file(file, object_document_id, upload_type, request.user.username))
    except Exception as e:
        return safe_error(e, success=False)


@login_required
def file_proxy(request, file_name):
    """문서 이미지 프록시 - S3 pre-signed URL로 리다이렉트"""
    try:
        url = get_file_proxy_url(file_name)
        if not url:
            return JsonResponse({'success': False, 'error': '파일을 찾을 수 없습니다.'}, status=404)
        return HttpResponseRedirect(url)
    except Exception as e:
        return safe_error(e, success=False)


@login_required
@require_POST
def file_delete(request, file_id):
    """첨부파일 개별 삭제 API (DB soft delete + S3 삭제)"""
    try:
        result = delete_file(file_id, request.user.username)
        if not result:
            return JsonResponse({'success': False, 'error': '파일을 찾을 수 없습니다.'})
        return JsonResponse(result)
    except Exception as e:
        return safe_error(e, success=False)


@login_required
def document_files(request):
    """문서 첨부파일 목록 조회 API"""
    object_document_id = request.GET.get('object_document_id', '')

    if not object_document_id:
        return JsonResponse({'success': False, 'error': 'object_document_id가 필요합니다.'})

    try:
        return JsonResponse(get_document_files(object_document_id))
    except Exception as e:
        return safe_error(e, success=False)


@login_required
@require_POST
def share_token(request):
    """문서 공유 토큰 생성 API (메모 필수, 매번 새 토큰 생성)"""
    try:
        data = json.loads(request.body)
        document_id = data.get('document_id', '').strip()
        category_id = data.get('category_id', '').strip()
        memo = data.get('memo', '').strip()

        if not document_id:
            return JsonResponse({'success': False, 'error': '문서 ID가 필요합니다.'})
        if not category_id:
            return JsonResponse({'success': False, 'error': '카테고리 ID가 필요합니다.'})
        if not memo:
            return JsonResponse({'success': False, 'error': '공유 대상 메모를 입력하세요.'})

        return JsonResponse(create_share_token(document_id, category_id, memo, request.user.username))
    except Exception as e:
        return safe_error(e, success=False)


@login_required
def share_list(request):
    """문서 공유 이력 조회 API (SQL 기반 상태 판단, 최근 20건)"""
    document_id = request.GET.get('document_id', '')
    if not document_id:
        return JsonResponse({'success': False, 'error': '문서 ID가 필요합니다.'})

    try:
        return JsonResponse(get_share_list(document_id))
    except Exception as e:
        return safe_error(e, success=False)


@login_required
@require_POST
def share_revoke(request):
    """공유 토큰 차단 API"""
    try:
        data = json.loads(request.body)
        token_id = data.get('token_id', '')
        if not token_id:
            return JsonResponse({'success': False, 'error': '토큰 ID가 필요합니다.'})

        updated = revoke_share_token(token_id, request.user.username)
        if updated == 0:
            return JsonResponse({'success': False, 'error': '이미 차단되었거나 존재하지 않는 토큰입니다.'})

        return JsonResponse({'success': True, 'message': '공유 링크가 차단되었습니다.'})
    except Exception as e:
        return safe_error(e, success=False)
