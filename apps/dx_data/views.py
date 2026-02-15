"""
DX 데이터 관리
- 아이템 마스터 관리 (is_product 분류)
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
        ],
    }
    return render(request, 'dx_data/item_master.html', context)
