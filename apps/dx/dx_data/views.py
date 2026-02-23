"""
DX 데이터 관리
- 아이템 마스터 관리 (is_product 분류)
- 변경 이력 조회
"""

from django.shortcuts import render, redirect


def index(request):
    """데이터 관리 인덱스 → 아이템 마스터로 리다이렉트"""
    return redirect('dx_data:item_master')


def item_master(request):
    """아이템 마스터 관리 페이지"""
    context = {
        'search_fields': [
            {'value': 'item', 'label': 'item'},
            {'value': 'sku', 'label': 'SKU'},
            {'value': 'product_url', 'label': 'URL'},
        ],
        'extra_filters': [
            {
                'id': 'filterProduct',
                'options': [
                    {'value': '', 'label': '제품여부 (전체)'},
                    {'value': 'true', 'label': '제품'},
                    {'value': 'false', 'label': '비제품'},
                ],
            },
            {
                'id': 'filterChecked',
                'options': [
                    {'value': '', 'label': '확인완료 (전체)'},
                    {'value': 'true', 'label': '확인완료'},
                    {'value': 'false', 'label': '미확인'},
                ],
            },
            {
                'id': 'filterAccount',
                'options': [
                    {'value': '', 'label': '리테일러 (전체)'},
                    {'value': 'Amazon', 'label': 'Amazon'},
                    {'value': 'Bestbuy', 'label': 'Bestbuy'},
                    {'value': 'Walmart', 'label': 'Walmart'},
                ],
            },
        ],
        'stat_list': [
            {'id': 'statTotal', 'label': '전체', 'value': 0},
            {'id': 'statProduct', 'label': '제품', 'value': 0},
            {'id': 'statNonProduct', 'label': '비제품', 'value': 0},
            {'id': 'statChecked', 'label': '확인완료', 'value': 0},
        ],
    }
    return render(request, 'dx_data/item_master.html', context)


def check_log(request):
    """검수 기록 페이지"""
    context = {
        'layer': {
            'number': 1,
            'name': '기본 통계 검수',
            'name_en': 'Foundational Integrity Check',
            'color': '#1a365d',
        },
    }
    return render(request, 'layer1/check_log.html', context)


def check_log_detail(request):
    """검수 기록 상세 페이지"""
    return render(request, 'layer1/check_log_detail.html')


def history(request):
    """변경 이력 페이지"""
    context = {
        'extra_filters': [
            {
                'id': 'filterField',
                'options': [
                    {'value': '', 'label': '변경 필드 (전체)'},
                    {'value': 'is_product', 'label': '제품여부'},
                    {'value': 'is_checked', 'label': '확인완료'},
                ],
            },
            {
                'id': 'filterAccount',
                'options': [
                    {'value': '', 'label': '리테일러 (전체)'},
                    {'value': 'Amazon', 'label': 'Amazon'},
                    {'value': 'Bestbuy', 'label': 'Bestbuy'},
                    {'value': 'Walmart', 'label': 'Walmart'},
                ],
            },
        ],
    }
    return render(request, 'dx_data/history.html', context)
