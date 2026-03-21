from django.shortcuts import render
from apps.dx.dx_layer4.common.context import build_context


def collection_status(request):
    """수집 현황"""
    return render(request, 'layer4/collection_status.html', build_context('collection_status', request))


def collection_status_detail(request):
    """수집 현황 — NULL 상세"""
    return render(request, 'layer4/collection_status_detail.html', build_context('collection_status', request))
