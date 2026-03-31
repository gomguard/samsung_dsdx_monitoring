"""
DS Document 뷰 (Thin Controller)
DS 문서 관리 (이슈보고서, 검수 보고서, 검수 매뉴얼 등)
"""

from django.shortcuts import render
from django.http import HttpResponse, HttpResponseNotFound
from .document import document_services as svc


def index(request):
    """DS 문서 페이지"""
    categories = svc.get_categories_context()
    context = {
        'data_source': {
            'id': 'ds',
            'name': 'DS Retail',
            'name_en': 'Global Price Tracking',
            'color': '#7c3aed',
        },
        'categories': categories,
    }
    return render(request, 'ds_document/index.html', context)


def edit(request, document_id=None):
    """DS 문서 편집 페이지"""
    editor_data = svc.get_editor_context(document_id, request.GET.get('category', ''), request.GET.get('type', 1))

    context = {
        'data_source': {
            'id': 'ds',
            'name': 'DS Retail',
            'name_en': 'Global Price Tracking',
            'color': '#7c3aed',
        },
        'document_id': document_id,
        'is_new': document_id is None,
        'categories': editor_data['categories'],
        'selected_category': editor_data['selected_category'],
        'selected_category_name': editor_data['selected_category_name'],
        'selected_category_type': editor_data['selected_category_type'],
        'template_content': editor_data['template_content'],
    }
    return render(request, 'ds_document/edit.html', context)


def share(request, token):
    """DS 문서 공유 페이지 (로그인 불필요, 1일 만료)"""
    result = svc.get_document_for_share(token)
    
    if not result.get('success'):
        return render(request, 'ds_document/share.html', {
            'error': result.get('error'),
            'error_type': result.get('error_type'),
        })

    return render(request, 'ds_document/share.html', {
        'document': result.get('document'),
    })


def share_file(request, token, file_name):
    """DS 공유 문서 이미지 프록시 (토큰 검증 후 S3에서 직접 전달)"""
    result = svc.get_file_binary_for_share(token, file_name)
    
    if not result.get('success'):
        return HttpResponseNotFound(result.get('error'))

    response = HttpResponse(result['file_data'], content_type=result['content_type'])
    response['Cache-Control'] = 'private, max-age=3600'
    return response
