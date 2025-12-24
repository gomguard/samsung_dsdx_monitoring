"""
Layer 2 API: 형식/NULL 검증 (Formatting & Null Validation)
- 검증유형별 분류: NULL검증, 형식검증, 이상치검증
- 테이블별 분류: TV Retail, HHP Retail, Sentiment, YouTube, Market
"""

import re
from django.http import JsonResponse
from datetime import datetime, timedelta
from apps.common.db import get_dx_connection


# 상태 기준: 0건 = OK, 1~10건 = WARNING, 10건 초과 = CRITICAL
def get_status(issue_count):
    if issue_count == 0:
        return 'OK'
    elif issue_count <= 10:
        return 'WARNING'
    else:
        return 'CRITICAL'


def validate_cross_field(row_data, account_name='Amazon'):
    """크로스 필드 논리 검증. 여러 필드 간 관계 검증. 오류 목록 반환"""
    errors = []

    star_rating = row_data.get('star_rating')
    count_of_star_ratings = row_data.get('count_of_star_ratings')
    page_type = row_data.get('page_type')
    main_rank = row_data.get('main_rank')
    bsr_rank = row_data.get('bsr_rank')
    final_sku_price = row_data.get('final_sku_price')
    original_sku_price = row_data.get('original_sku_price')

    # 리테일러별 리뷰없음 텍스트
    if account_name == 'Amazon':
        no_review_texts = ['No customer reviews']
    elif account_name == 'Bestbuy':
        no_review_texts = ['Not yet reviewed']
    else:  # Walmart
        no_review_texts = ['No ratings yet']

    # 1. star_rating 값이 있는데 count_of_star_ratings가 0 또는 NULL
    if star_rating is not None and str(star_rating).strip() != '' and str(star_rating).strip() not in no_review_texts:
        try:
            rating_val = float(star_rating)
            if rating_val > 0:
                # count_of_star_ratings가 NULL이거나 빈값이거나 0인 경우
                if count_of_star_ratings is None or str(count_of_star_ratings).strip() == '':
                    errors.append({
                        'field': 'star_rating ↔ count_of_star_ratings',
                        'value': f'star_rating={star_rating}, count_of_star_ratings=NULL',
                        'error': 'star_rating 값이 있는데 count_of_star_ratings가 NULL'
                    })
                elif str(count_of_star_ratings).strip() not in no_review_texts:
                    clean_count = str(count_of_star_ratings).replace(',', '')
                    if clean_count.isdigit() and int(clean_count) == 0:
                        errors.append({
                            'field': 'star_rating ↔ count_of_star_ratings',
                            'value': f'star_rating={star_rating}, count_of_star_ratings=0',
                            'error': 'star_rating 값이 있는데 count_of_star_ratings가 0'
                        })
        except (ValueError, TypeError):
            pass

    # 2. page_type이 'main'인데 main_rank가 NULL
    if page_type is not None and str(page_type).strip() == 'main':
        if main_rank is None or str(main_rank).strip() == '':
            errors.append({
                'field': 'page_type ↔ main_rank',
                'value': f'page_type=main, main_rank=NULL',
                'error': 'page_type이 main인데 main_rank가 NULL'
            })

    # 3. page_type이 'bsr'인데 bsr_rank가 NULL
    if page_type is not None and str(page_type).strip() == 'bsr':
        if bsr_rank is None or str(bsr_rank).strip() == '':
            errors.append({
                'field': 'page_type ↔ bsr_rank',
                'value': f'page_type=bsr, bsr_rank=NULL',
                'error': 'page_type이 bsr인데 bsr_rank가 NULL'
            })

    # 3-1. page_type이 'promotion'인데 promotion_rank가 NULL (Bestbuy TV)
    promotion_rank = row_data.get('promotion_rank')
    if page_type is not None and str(page_type).strip() == 'promotion':
        if promotion_rank is None or str(promotion_rank).strip() == '':
            errors.append({
                'field': 'page_type ↔ promotion_rank',
                'value': f'page_type=promotion, promotion_rank=NULL',
                'error': 'page_type이 promotion인데 promotion_rank가 NULL'
            })

    # 3-2. page_type이 'trend'인데 trend_rank가 NULL (Bestbuy HHP)
    trend_rank = row_data.get('trend_rank')
    if page_type is not None and str(page_type).strip() == 'trend':
        if trend_rank is None or str(trend_rank).strip() == '':
            errors.append({
                'field': 'page_type ↔ trend_rank',
                'value': f'page_type=trend, trend_rank=NULL',
                'error': 'page_type이 trend인데 trend_rank가 NULL'
            })

    # 4. final_sku_price > original_sku_price (할인인데 더 비싼 경우)
    if final_sku_price is not None and original_sku_price is not None:
        final_str = str(final_sku_price).strip()
        original_str = str(original_sku_price).strip()

        # 둘 다 가격 형식인 경우만 비교 ($로 시작하는 숫자)
        if final_str.startswith('$') and original_str.startswith('$'):
            try:
                # $ 제거하고 숫자만 추출
                final_val = float(final_str.replace('$', '').replace(',', '').split('/')[0])
                original_val = float(original_str.replace('$', '').replace(',', '').split('/')[0])

                if final_val > original_val:
                    errors.append({
                        'field': 'final_sku_price ↔ original_sku_price',
                        'value': f'final={final_str}, original={original_str}',
                        'error': f'final_sku_price({final_str})가 original_sku_price({original_str})보다 높음'
                    })
            except (ValueError, TypeError):
                pass

    return errors


def validate_tv_field(field_name, value, account_name='Amazon'):
    """TV Retail 필드별 형식 검증. 오류 시 메시지 반환, 정상이면 None"""
    if value is None:
        return None
    val = str(value).strip()
    if val == '':
        return None

    # ======== 공통 검증 ========
    # item: 알파벳+숫자
    if field_name == 'item':
        if not re.match(r'^[A-Za-z0-9]+$', val):
            return f'item 형식 오류: {val[:20]}'

    # account_name: Amazon, Bestbuy, Walmart
    elif field_name == 'account_name':
        if val not in ['Amazon', 'Bestbuy', 'Walmart']:
            return f'account_name 오류: {val}'

    # page_type: main, bsr, trend, promotion
    elif field_name == 'page_type':
        if val not in ['main', 'bsr', 'trend', 'promotion']:
            return f'page_type 오류: {val}'

    # product_url: http 시작
    elif field_name == 'product_url':
        if not val.startswith('http://') and not val.startswith('https://'):
            return 'product_url 형식 오류'

    # main_rank: 1~400 (TV는 400까지)
    elif field_name == 'main_rank':
        try:
            rank = int(val)
            if rank < 1 or rank > 400:
                return f'main_rank 범위 오류: {val} (1~400)'
        except ValueError:
            return f'main_rank 숫자 아님: {val}'

    # bsr_rank: 1~100
    elif field_name == 'bsr_rank':
        try:
            rank = int(val)
            if rank < 1 or rank > 100:
                return f'bsr_rank 범위 오류: {val} (1~100)'
        except ValueError:
            return f'bsr_rank 숫자 아님: {val}'

    # final_sku_price, original_sku_price: $00.00 형식 (리테일러별)
    elif field_name in ['final_sku_price', 'original_sku_price']:
        amazon_allowed = ['No featured offers available', 'Currently unavailable.', 'Price higher than typical',
                          'To see our price, add this item to your cart.', 'See price in cart']
        bestbuy_allowed = ['See price in cart']
        walmart_allowed = ['Not Available', 'See price in cart']

        if account_name == 'Amazon' and val in amazon_allowed:
            return None
        elif account_name == 'Bestbuy' and val in bestbuy_allowed:
            return None
        elif account_name == 'Walmart' and val in walmart_allowed:
            return None
        elif account_name == 'Walmart' and re.match(r'^\$[\d,]+\.?\d*/(month|undefined)$', val):
            return None
        elif not re.match(r'^\$[\d,]+\.?\d*$', val):
            return f'{field_name} 형식 오류: {val[:20]}'

    # count_of_reviews: 숫자(쉼표 가능)
    elif field_name == 'count_of_reviews':
        clean_val = val.replace(',', '')
        if not re.match(r'^\d+$', clean_val):
            return f'count_of_reviews 형식 오류: {val[:20]}'

    # star_rating: 0.0~5.0 또는 리뷰없음 텍스트 (리테일러별 허용값 다름)
    elif field_name == 'star_rating':
        # Amazon TV: No customer reviews 만 허용
        # Bestbuy TV: Not yet reviewed 만 허용
        # Walmart TV: No ratings yet 만 허용
        if account_name == 'Amazon':
            no_review_texts = ['No customer reviews']
        elif account_name == 'Bestbuy':
            no_review_texts = ['Not yet reviewed']
        else:  # Walmart
            no_review_texts = ['No ratings yet']
        if val in no_review_texts:
            return None
        try:
            rating = float(val)
            if rating < 0.0 or rating > 5.0:
                return f'star_rating 범위 오류: {val} (0.0~5.0)'
        except ValueError:
            return f'star_rating 형식 오류: {val[:20]}'

    # count_of_star_ratings: 숫자(쉼표 가능) 또는 리뷰없음 텍스트 (리테일러별 허용값 다름)
    elif field_name == 'count_of_star_ratings':
        # Amazon TV: No customer reviews 만 허용
        # Bestbuy TV: Not yet reviewed 만 허용
        # Walmart TV: No ratings yet 만 허용
        if account_name == 'Amazon':
            no_review_texts = ['No customer reviews']
        elif account_name == 'Bestbuy':
            no_review_texts = ['Not yet reviewed']
        else:  # Walmart
            no_review_texts = ['No ratings yet']
        if val in no_review_texts:
            return None
        clean_val = val.replace(',', '')
        if not re.match(r'^\d+$', clean_val):
            return f'count_of_star_ratings 형식 오류: {val[:20]}'

    # detailed_review_content: TV는 1- 로 시작 (Amazon), review1- (Walmart)
    elif field_name == 'detailed_review_content':
        if account_name == 'Amazon' and val == 'No customer reviews':
            return None
        elif account_name == 'Amazon' and val and not val.startswith('1-'):
            return 'detailed_review_content 형식 오류 (1- 로 시작해야 함)'
        elif account_name == 'Walmart' and val and not val.startswith('review1-'):
            return 'detailed_review_content 형식 오류 (review1- 로 시작해야 함)'
        elif account_name == 'Bestbuy' and val and not val.startswith('review1 - '):
            return 'detailed_review_content 형식 오류 (review1 - 로 시작해야 함)'

    # ======== Amazon 전용 검증 ========
    elif account_name == 'Amazon':
        # number_of_units_purchased_past_month: 숫자
        if field_name == 'number_of_units_purchased_past_month':
            clean_val = val.replace(',', '').replace('+', '')
            if not re.match(r'^\d+$', clean_val) and val.lower() not in ['null', 'none']:
                return f'number_of_units_purchased_past_month 형식 오류: {val[:20]}'

        # available_quantity_for_purchase: 숫자 또는 "In Stock"
        elif field_name == 'available_quantity_for_purchase':
            clean_val = val.replace(',', '')
            if not re.match(r'^\d+$', clean_val) and val != 'In Stock':
                return f'available_quantity_for_purchase 형식 오류: {val[:20]}'

        # sku_popularity: Amazon's Choice 또는 null/빈값
        elif field_name == 'sku_popularity':
            if val and val not in ["Amazon's  Choice", "Amazon's Choice"]:
                return f"sku_popularity 오류: {val[:20]}"

        # retailer_membership_discounts: Prime members 시작 (TV Amazon은 Or 없음)
        elif field_name == 'retailer_membership_discounts':
            if val and not val.startswith('Prime members'):
                return f'retailer_membership_discounts 형식 오류: {val[:20]}'

        # rank_1, rank_2: # 시작
        elif field_name in ['rank_1', 'rank_2']:
            if val and not val.startswith('#'):
                return f'{field_name} 형식 오류 (# 로 시작해야 함)'

        # summarized_review_content: Customers 시작
        elif field_name == 'summarized_review_content':
            if val and not val.startswith('Customers'):
                return f'summarized_review_content 형식 오류 (Customers 로 시작해야 함)'

    # ======== Bestbuy 전용 검증 ========
    elif account_name == 'Bestbuy':
        # savings: $00.00 형식
        if field_name == 'savings':
            if not re.match(r'^\$[\d,]+\.?\d*$', val):
                return f'savings 형식 오류: {val[:20]}'

        # offer: 숫자 형식
        elif field_name == 'offer':
            if not re.match(r'^\d+$', val):
                return f'offer 형식 오류: {val[:20]}'

        # retailer_sku_name_similar: null이거나 구분자 ||| 3개 존재
        elif field_name == 'retailer_sku_name_similar':
            if val:
                separator_count = val.count('|||')
                if separator_count != 3:
                    return f'retailer_sku_name_similar 오류 (||| 구분자 {separator_count}개, 3개 필요)'

        # recommendation_intent: 숫자% would recommend to a friend 형식
        elif field_name == 'recommendation_intent':
            if val and not re.match(r'^\d+% would recommend to a friend$', val):
                return f'recommendation_intent 형식 오류: {val[:30]}'

    # ======== Walmart 전용 검증 ========
    elif account_name == 'Walmart':
        # offer: 숫자
        if field_name == 'offer':
            if not re.match(r'^\d+$', val):
                return f'offer 형식 오류: {val[:20]}'

        # retailer_membership_discounts: Walmart Plus 또는 Save with W+ 만 허용
        elif field_name == 'retailer_membership_discounts':
            if val and not (val == 'Walmart Plus' or val.startswith('Save with W+')):
                return f'retailer_membership_discounts 형식 오류: {val[:20]}'

        # available_quantity_for_purchase: 숫자
        elif field_name == 'available_quantity_for_purchase':
            clean_val = val.replace(',', '')
            if not re.match(r'^\d+$', clean_val):
                return f'available_quantity_for_purchase 형식 오류: {val[:20]}'

        # number_of_ppl_purchased_yesterday: 숫자
        elif field_name == 'number_of_ppl_purchased_yesterday':
            clean_val = val.replace(',', '').replace('+', '')
            if not re.match(r'^\d+$', clean_val):
                return f'number_of_ppl_purchased_yesterday 형식 오류: {val[:20]}'

        # number_of_ppl_added_to_carts: 숫자
        elif field_name == 'number_of_ppl_added_to_carts':
            clean_val = val.replace(',', '').replace('+', '')
            if not re.match(r'^\d+$', clean_val):
                return f'number_of_ppl_added_to_carts 형식 오류: {val[:20]}'

        # savings: $00.00 형식
        elif field_name == 'savings':
            if not re.match(r'^\$[\d,]+\.?\d*$', val):
                return f'savings 형식 오류: {val[:20]}'

        # discount_type: Price when purchased online 또는 null
        elif field_name == 'discount_type':
            if val and val != 'Price when purchased online':
                return f'discount_type 오류: {val[:20]}'

    return None


def validate_hhp_field(field_name, value, account_name='Amazon'):
    """HHP Retail 필드별 형식 검증 (TV와 다른 검증 규칙 적용)"""
    if value is None:
        return None
    val = str(value).strip()
    if val == '':
        return None

    # ======== 공통 검증 ========
    # item: 알파벳+숫자
    if field_name == 'item':
        if not re.match(r'^[A-Za-z0-9]+$', val):
            return f'item 형식 오류: {val[:20]}'

    # account_name: Amazon, Bestbuy, Walmart
    elif field_name == 'account_name':
        if val not in ['Amazon', 'Bestbuy', 'Walmart']:
            return f'account_name 오류: {val}'

    # page_type: main, bsr, trend (HHP는 promotion 없음)
    elif field_name == 'page_type':
        if val not in ['main', 'bsr', 'trend']:
            return f'page_type 오류: {val}'

    # product_url: http 시작
    elif field_name == 'product_url':
        if not val.startswith('http://') and not val.startswith('https://'):
            return 'product_url 형식 오류'

    # main_rank: 1~300 (HHP는 300까지)
    elif field_name == 'main_rank':
        try:
            rank = int(val)
            if rank < 1 or rank > 300:
                return f'main_rank 범위 오류: {val} (1~300)'
        except ValueError:
            return f'main_rank 숫자 아님: {val}'

    # bsr_rank: 1~100
    elif field_name == 'bsr_rank':
        try:
            rank = int(val)
            if rank < 1 or rank > 100:
                return f'bsr_rank 범위 오류: {val} (1~100)'
        except ValueError:
            return f'bsr_rank 숫자 아님: {val}'

    # trend_rank: 1~10 (HHP 전용)
    elif field_name == 'trend_rank':
        try:
            rank = int(val)
            if rank < 1 or rank > 10:
                return f'trend_rank 범위 오류: {val} (1~10)'
        except ValueError:
            return f'trend_rank 숫자 아님: {val}'

    # final_sku_price, original_sku_price: $00.00 형식 (리테일러별)
    elif field_name in ['final_sku_price', 'original_sku_price']:
        amazon_allowed = ['No featured offers available', 'Currently unavailable.', 'Price higher than typical', 'To see our price, add this item to your cart.', 'See price in cart']
        walmart_allowed = ['Not Available']

        if account_name == 'Amazon' and val in amazon_allowed:
            return None
        elif account_name == 'Walmart' and val in walmart_allowed:
            return None
        elif account_name == 'Walmart' and re.match(r'^\$[\d,]+\.?\d*/(month|undefined)$', val):
            return None
        elif not re.match(r'^\$[\d,]+\.?\d*$', val):
            return f'{field_name} 형식 오류: {val[:20]}'

    # count_of_reviews: 숫자(쉼표 가능)
    elif field_name == 'count_of_reviews':
        clean_val = val.replace(',', '')
        if not re.match(r'^\d+$', clean_val):
            return f'count_of_reviews 형식 오류: {val[:20]}'

    # star_rating: 0.0~5.0 또는 리뷰없음 텍스트 (리테일러별 허용값 다름)
    elif field_name == 'star_rating':
        # Amazon HHP: No customer reviews 만 허용
        # Bestbuy HHP: Not yet reviewed 만 허용
        # Walmart HHP: No ratings yet 만 허용
        if account_name == 'Amazon':
            no_review_texts = ['No customer reviews']
        elif account_name == 'Bestbuy':
            no_review_texts = ['Not yet reviewed']
        else:  # Walmart
            no_review_texts = ['No ratings yet']
        if val in no_review_texts:
            return None
        try:
            rating = float(val)
            if rating < 0.0 or rating > 5.0:
                return f'star_rating 범위 오류: {val} (0.0~5.0)'
        except ValueError:
            return f'star_rating 형식 오류: {val[:20]}'

    # count_of_star_ratings: 숫자(쉼표 가능) 또는 리뷰없음 텍스트 (리테일러별 허용값 다름)
    elif field_name == 'count_of_star_ratings':
        # Amazon HHP: No customer reviews 만 허용
        # Bestbuy HHP: Not yet reviewed 만 허용
        # Walmart HHP: No ratings yet 만 허용
        if account_name == 'Amazon':
            no_review_texts = ['No customer reviews']
        elif account_name == 'Bestbuy':
            no_review_texts = ['Not yet reviewed']
        else:  # Walmart
            no_review_texts = ['No ratings yet']
        if val in no_review_texts:
            return None
        clean_val = val.replace(',', '')
        if not re.match(r'^\d+$', clean_val):
            return f'count_of_star_ratings 형식 오류: {val[:20]}'

    # detailed_review_content: HHP는 review1 - 로 시작 (Amazon, Bestbuy 공통)
    elif field_name == 'detailed_review_content':
        if account_name == 'Amazon' and val == 'No customer reviews':
            return None
        elif val and not val.startswith('review1 - '):
            return 'detailed_review_content 형식 오류 (review1 - 로 시작해야 함)'

    # ======== Amazon 전용 검증 ========
    elif account_name == 'Amazon':
        # number_of_units_purchased_past_month: 숫자
        if field_name == 'number_of_units_purchased_past_month':
            clean_val = val.replace(',', '').replace('+', '')
            if not re.match(r'^\d+$', clean_val) and val.lower() not in ['null', 'none']:
                return f'number_of_units_purchased_past_month 형식 오류: {val[:20]}'

        # available_quantity_for_purchase: 숫자
        elif field_name == 'available_quantity_for_purchase':
            clean_val = val.replace(',', '')
            if not re.match(r'^\d+$', clean_val):
                return f'available_quantity_for_purchase 형식 오류: {val[:20]}'

        # sku_popularity: Amazon's Choice 또는 null/빈값
        elif field_name == 'sku_popularity':
            if val and val not in ["Amazon's  Choice", "Amazon's Choice"]:
                return f"sku_popularity 오류: {val[:20]}"

        # trade_in: Save up to $ 시작 (HHP Amazon 전용)
        elif field_name == 'trade_in':
            if val and not val.startswith('Save up to $'):
                return f'trade_in 형식 오류 (Save up to $ 로 시작해야 함)'

        # retailer_membership_discounts: Or Prime members 시작
        elif field_name == 'retailer_membership_discounts':
            if val and not val.startswith('Or Prime members'):
                return f'retailer_membership_discounts 형식 오류: {val[:20]}'

        # rank_1, rank_2: # 시작
        elif field_name in ['rank_1', 'rank_2']:
            if val and not val.startswith('#'):
                return f'{field_name} 형식 오류 (# 로 시작해야 함)'

        # summarized_review_content: Customers 시작
        elif field_name == 'summarized_review_content':
            if val and not val.startswith('Customers'):
                return f'summarized_review_content 형식 오류 (Customers 로 시작해야 함)'

    # ======== Bestbuy 전용 검증 ========
    elif account_name == 'Bestbuy':
        # savings: $00.00 형식
        if field_name == 'savings':
            if not re.match(r'^\$[\d,]+\.?\d*$', val):
                return f'savings 형식 오류: {val[:20]}'

        # offer: 숫자 형식
        elif field_name == 'offer':
            if not re.match(r'^\d+$', val):
                return f'offer 형식 오류: {val[:20]}'

        # sku_status: Sponsored 또는 null (HHP Bestbuy 전용)
        elif field_name == 'sku_status':
            if val and val != 'Sponsored':
                return f'sku_status 오류 (Sponsored 또는 null)'

        # trade_in: Check your trade-in value. 시작 (HHP Bestbuy 전용)
        elif field_name == 'trade_in':
            if val and not val.startswith('Check your trade-in value.'):
                return f'trade_in 형식 오류 (Check your trade-in value. 로 시작해야 함)'

        # retailer_sku_name_similar: null이거나 구분자 ||| 3개 존재
        elif field_name == 'retailer_sku_name_similar':
            if val:
                separator_count = val.count('|||')
                if separator_count != 3:
                    return f'retailer_sku_name_similar 오류 (||| 구분자 {separator_count}개, 3개 필요)'

        # recommendation_intent: 숫자% would recommend to a friend 형식
        elif field_name == 'recommendation_intent':
            if val and not re.match(r'^\d+% would recommend to a friend$', val):
                return f'recommendation_intent 형식 오류: {val[:30]}'

    # ======== Walmart 전용 검증 ========
    elif account_name == 'Walmart':
        # offer: 숫자
        if field_name == 'offer':
            if not re.match(r'^\d+$', val):
                return f'offer 형식 오류: {val[:20]}'

        # retailer_membership_discounts: Save with W+ 시작
        elif field_name == 'retailer_membership_discounts':
            if val and not val.startswith('Save with W+'):
                return f'retailer_membership_discounts 형식 오류: {val[:20]}'

        # available_quantity_for_purchase: 숫자
        elif field_name == 'available_quantity_for_purchase':
            clean_val = val.replace(',', '')
            if not re.match(r'^\d+$', clean_val):
                return f'available_quantity_for_purchase 형식 오류: {val[:20]}'

        # number_of_ppl_purchased_yesterday: 숫자
        elif field_name == 'number_of_ppl_purchased_yesterday':
            clean_val = val.replace(',', '').replace('+', '')
            if not re.match(r'^\d+$', clean_val):
                return f'number_of_ppl_purchased_yesterday 형식 오류: {val[:20]}'

        # number_of_ppl_added_to_carts: 숫자
        elif field_name == 'number_of_ppl_added_to_carts':
            clean_val = val.replace(',', '').replace('+', '')
            if not re.match(r'^\d+$', clean_val):
                return f'number_of_ppl_added_to_carts 형식 오류: {val[:20]}'

        # savings: $00.00 형식
        elif field_name == 'savings':
            if not re.match(r'^\$[\d,]+\.?\d*$', val):
                return f'savings 형식 오류: {val[:20]}'

        # discount_type: Price when purchased online 또는 null
        elif field_name == 'discount_type':
            if val and val != 'Price when purchased online':
                return f'discount_type 오류: {val[:20]}'

    return None


def layer_stats(request):
    """Layer 2 통계 API - 검증유형별, 테이블별 구조화"""
    date_str = request.GET.get('date')

    if date_str:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    else:
        target_date = (datetime.now() - timedelta(days=1)).date()

    next_date = target_date + timedelta(days=1)

    results = {
        'timestamp': datetime.now().isoformat(),
        'date': str(target_date),
        'layer': 2,
        'name': '형식/NULL 검수',
        'validation_types': [],
        'summary': {
            'total_issues': 0,
            'null_issues': 0,
            'format_issues': 0,
            'duplicate_issues': 0,
            'overall_status': 'OK'
        }
    }

    try:
        conn = get_dx_connection()
        cursor = conn.cursor()

        total_null_issues = 0
        total_format_issues = 0
        total_anomaly_issues = 0

        # ============================================================
        # 1. NULL 검증 (필수값 누락)
        # ============================================================
        null_validation = {
            'type': 'null',
            'type_name': 'NULL 검증',
            'type_name_en': 'Null Validation',
            'description': '필수 필드의 NULL 또는 빈값 검증',
            'icon': '🔍',
            'tables': []
        }

        # TV Retail NULL 검증 - 필수항목별 NULL 개수 + 하나라도 NULL인 레코드 수
        cursor.execute("""
            SELECT
                account_name,
                COUNT(*) as total,
                COUNT(CASE WHEN item IS NULL OR item = '' THEN 1 END) as null_item,
                COUNT(CASE WHEN screen_size IS NULL OR screen_size = '' THEN 1 END) as null_screen_size,
                COUNT(CASE WHEN final_sku_price IS NULL OR final_sku_price = '' THEN 1 END) as null_price,
                COUNT(CASE WHEN retailer_sku_name IS NULL OR retailer_sku_name = '' THEN 1 END) as null_sku_name,
                COUNT(CASE WHEN count_of_reviews IS NULL OR count_of_reviews = '' THEN 1 END) as null_reviews,
                COUNT(CASE WHEN star_rating IS NULL OR star_rating = '' THEN 1 END) as null_rating,
                COUNT(CASE WHEN count_of_star_ratings IS NULL OR count_of_star_ratings = '' THEN 1 END) as null_star_ratings,
                COUNT(CASE WHEN (item IS NULL OR item = '')
                              OR (screen_size IS NULL OR screen_size = '')
                              OR (final_sku_price IS NULL OR final_sku_price = '')
                              OR (retailer_sku_name IS NULL OR retailer_sku_name = '')
                              OR (count_of_reviews IS NULL OR count_of_reviews = '')
                              OR (star_rating IS NULL OR star_rating = '')
                              OR (count_of_star_ratings IS NULL OR count_of_star_ratings = '')
                         THEN 1 END) as records_with_null
            FROM tv_retail_com
            WHERE DATE(crawl_datetime::timestamp) = %s
            GROUP BY account_name
            ORDER BY account_name
        """, (target_date,))

        tv_null_rows = cursor.fetchall()
        tv_null_retailers = []
        tv_null_total = 0
        tv_null_issue_total = 0

        for row in tv_null_rows:
            records_with_null = row[9]  # 하나라도 NULL인 레코드 수
            tv_null_retailers.append({
                'retailer': row[0],
                'total': row[1],
                'records_with_null': records_with_null,
                'fields_detail': {
                    'item': row[2],
                    'screen_size': row[3],
                    'final_sku_price': row[4],
                    'retailer_sku_name': row[5],
                    'count_of_reviews': row[6],
                    'star_rating': row[7],
                    'count_of_star_ratings': row[8]
                },
                'status': get_status(records_with_null)
            })
            tv_null_total += row[1]
            tv_null_issue_total += records_with_null

        null_validation['tables'].append({
            'table': 'tv_retail',
            'table_name': 'TV Retail',
            'total_records': tv_null_total,
            'total_issues': tv_null_issue_total,
            'status': get_status(tv_null_issue_total),
            'retailers': tv_null_retailers,
            'fields': ['item', 'screen_size', 'final_sku_price', 'retailer_sku_name', 'count_of_reviews', 'star_rating', 'count_of_star_ratings']
        })
        total_null_issues += tv_null_issue_total

        # HHP Retail NULL 검증 - 필수항목별 NULL 개수 + 하나라도 NULL인 레코드 수
        cursor.execute("""
            SELECT
                account_name,
                COUNT(*) as total,
                COUNT(CASE WHEN item IS NULL OR item = '' THEN 1 END) as null_item,
                COUNT(CASE WHEN final_sku_price IS NULL OR final_sku_price = '' THEN 1 END) as null_price,
                COUNT(CASE WHEN retailer_sku_name IS NULL OR retailer_sku_name = '' THEN 1 END) as null_sku_name,
                COUNT(CASE WHEN count_of_reviews IS NULL OR count_of_reviews = '' THEN 1 END) as null_reviews,
                COUNT(CASE WHEN star_rating IS NULL OR star_rating = '' THEN 1 END) as null_rating,
                COUNT(CASE WHEN count_of_star_ratings IS NULL OR count_of_star_ratings = '' THEN 1 END) as null_star_ratings,
                COUNT(CASE WHEN (item IS NULL OR item = '')
                              OR (final_sku_price IS NULL OR final_sku_price = '')
                              OR (retailer_sku_name IS NULL OR retailer_sku_name = '')
                              OR (count_of_reviews IS NULL OR count_of_reviews = '')
                              OR (star_rating IS NULL OR star_rating = '')
                              OR (count_of_star_ratings IS NULL OR count_of_star_ratings = '')
                         THEN 1 END) as records_with_null
            FROM hhp_retail_com
            WHERE DATE(crawl_strdatetime::timestamp) = %s
            GROUP BY account_name
            ORDER BY account_name
        """, (target_date,))

        hhp_null_rows = cursor.fetchall()
        hhp_null_retailers = []
        hhp_null_total = 0
        hhp_null_issue_total = 0

        for row in hhp_null_rows:
            records_with_null = row[8]  # 하나라도 NULL인 레코드 수
            hhp_null_retailers.append({
                'retailer': row[0],
                'total': row[1],
                'records_with_null': records_with_null,
                'fields_detail': {
                    'item': row[2],
                    'final_sku_price': row[3],
                    'retailer_sku_name': row[4],
                    'count_of_reviews': row[5],
                    'star_rating': row[6],
                    'count_of_star_ratings': row[7]
                },
                'status': get_status(records_with_null)
            })
            hhp_null_total += row[1]
            hhp_null_issue_total += records_with_null

        null_validation['tables'].append({
            'table': 'hhp_retail',
            'table_name': 'HHP Retail',
            'total_records': hhp_null_total,
            'total_issues': hhp_null_issue_total,
            'status': get_status(hhp_null_issue_total),
            'retailers': hhp_null_retailers,
            'fields': ['item', 'final_sku_price', 'retailer_sku_name', 'count_of_reviews', 'star_rating', 'count_of_star_ratings']
        })
        total_null_issues += hhp_null_issue_total

        # YouTube NULL 검증 (Logs, Videos, Comments 통합)
        # Logs NULL 검증
        cursor.execute("""
            SELECT
                COUNT(*) as total,
                COUNT(CASE WHEN keyword_id IS NULL THEN 1 END) as null_keyword_id,
                COUNT(CASE WHEN keyword IS NULL OR keyword = '' THEN 1 END) as null_keyword,
                COUNT(CASE WHEN status IS NULL OR status = '' THEN 1 END) as null_status,
                COUNT(CASE WHEN videos_collected IS NULL THEN 1 END) as null_videos_collected,
                COUNT(CASE WHEN comments_collected IS NULL THEN 1 END) as null_comments_collected,
                COUNT(CASE WHEN started_at IS NULL THEN 1 END) as null_started_at,
                COUNT(CASE WHEN completed_at IS NULL THEN 1 END) as null_completed_at
            FROM youtube_collection_logs
            WHERE DATE(started_at) = %s
        """, (target_date,))
        yt_log_null_row = cursor.fetchone()
        yt_log_null_issues = (yt_log_null_row[1] or 0) + (yt_log_null_row[2] or 0) + (yt_log_null_row[3] or 0) + (yt_log_null_row[6] or 0) + (yt_log_null_row[7] or 0)

        # Videos NULL 검증
        cursor.execute("""
            SELECT
                COUNT(*) as total,
                COUNT(CASE WHEN video_id IS NULL OR video_id = '' THEN 1 END) as null_video_id,
                COUNT(CASE WHEN keyword IS NULL OR keyword = '' THEN 1 END) as null_keyword,
                COUNT(CASE WHEN title IS NULL OR title = '' THEN 1 END) as null_title,
                COUNT(CASE WHEN published_at IS NULL THEN 1 END) as null_published_at,
                COUNT(CASE WHEN channel_country IS NULL OR channel_country = '' THEN 1 END) as null_channel_country
            FROM youtube_videos
            WHERE DATE(created_at) = %s
        """, (target_date,))
        yt_video_null_row = cursor.fetchone()
        yt_video_null_issues = (yt_video_null_row[1] or 0) + (yt_video_null_row[2] or 0) + (yt_video_null_row[3] or 0) + (yt_video_null_row[4] or 0) + (yt_video_null_row[5] or 0)

        # Comments NULL 검증
        cursor.execute("""
            SELECT
                COUNT(*) as total,
                COUNT(CASE WHEN comment_id IS NULL OR comment_id = '' THEN 1 END) as null_comment_id,
                COUNT(CASE WHEN video_id IS NULL OR video_id = '' THEN 1 END) as null_video_id,
                COUNT(CASE WHEN comment_text_display IS NULL OR comment_text_display = '' THEN 1 END) as null_comment_text,
                COUNT(CASE WHEN published_at IS NULL THEN 1 END) as null_published_at
            FROM youtube_comments
            WHERE DATE(created_at) = %s
        """, (target_date,))
        yt_comment_null_row = cursor.fetchone()
        yt_comment_null_issues = (yt_comment_null_row[1] or 0) + (yt_comment_null_row[2] or 0) + (yt_comment_null_row[3] or 0) + (yt_comment_null_row[4] or 0)

        # YouTube 통합 (리테일러 형태로) - 순서: Logs, Videos, Comments
        yt_total_null_issues = yt_log_null_issues + yt_video_null_issues + yt_comment_null_issues
        yt_total_records = (yt_log_null_row[0] or 0) + (yt_video_null_row[0] or 0) + (yt_comment_null_row[0] or 0)

        youtube_null_retailers = [
            {
                'retailer': 'Logs',
                'total': yt_log_null_row[0] or 0,
                'records_with_null': yt_log_null_issues,
                'status': get_status(yt_log_null_issues),
                'fields_detail': {
                    'keyword_id': yt_log_null_row[1] or 0,
                    'keyword': yt_log_null_row[2] or 0,
                    'status': yt_log_null_row[3] or 0,
                    'videos_collected': yt_log_null_row[4] or 0,
                    'comments_collected': yt_log_null_row[5] or 0,
                    'started_at': yt_log_null_row[6] or 0,
                    'completed_at': yt_log_null_row[7] or 0
                }
            },
            {
                'retailer': 'Videos',
                'total': yt_video_null_row[0] or 0,
                'records_with_null': yt_video_null_issues,
                'status': get_status(yt_video_null_issues),
                'fields_detail': {
                    'video_id': yt_video_null_row[1] or 0,
                    'keyword': yt_video_null_row[2] or 0,
                    'title': yt_video_null_row[3] or 0,
                    'published_at': yt_video_null_row[4] or 0,
                    'channel_country': yt_video_null_row[5] or 0
                }
            },
            {
                'retailer': 'Comments',
                'total': yt_comment_null_row[0] or 0,
                'records_with_null': yt_comment_null_issues,
                'status': get_status(yt_comment_null_issues),
                'fields_detail': {
                    'comment_id': yt_comment_null_row[1] or 0,
                    'video_id': yt_comment_null_row[2] or 0,
                    'comment_text_display': yt_comment_null_row[3] or 0,
                    'published_at': yt_comment_null_row[4] or 0
                }
            }
        ]

        null_validation['tables'].append({
            'table': 'youtube',
            'table_name': 'YouTube',
            'total_records': yt_total_records,
            'total_issues': yt_total_null_issues,
            'status': get_status(yt_total_null_issues),
            'retailers': youtube_null_retailers,
            'fields': ['comment_id', 'video_id', 'keyword', 'title', 'published_at', 'channel_country', 'keyword_id', 'status', 'started_at', 'completed_at', 'comment_text_display']
        })
        total_null_issues += yt_total_null_issues

        # Market NULL 검증 (Trend, Comp Product, Comp Event)
        try:
            # market_trend NULL 검증
            cursor.execute("""
                SELECT
                    COUNT(*) as total,
                    COUNT(CASE WHEN keyword IS NULL OR keyword = '' THEN 1 END) as null_keyword,
                    COUNT(CASE WHEN total_article_number IS NULL THEN 1 END) as null_total_article_number,
                    COUNT(CASE WHEN calendar_week IS NULL OR calendar_week = '' THEN 1 END) as null_calendar_week,
                    COUNT(CASE WHEN crawl_at_local_time IS NULL THEN 1 END) as null_crawl_at_local_time
                FROM market_trend
                WHERE DATE(crawl_at_local_time) = %s
            """, (target_date,))
            market_trend_null_row = cursor.fetchone()
            market_trend_total = market_trend_null_row[0] if market_trend_null_row else 0
            market_trend_null_issues = sum(v or 0 for v in market_trend_null_row[1:5]) if market_trend_null_row else 0

            # market_comp_product NULL 검증
            cursor.execute("""
                SELECT
                    COUNT(*) as total,
                    COUNT(CASE WHEN country IS NULL OR country = '' THEN 1 END) as null_country,
                    COUNT(CASE WHEN samsung_series_name IS NULL OR samsung_series_name = '' THEN 1 END) as null_samsung_series_name,
                    COUNT(CASE WHEN comp_brand IS NULL OR comp_brand = '' THEN 1 END) as null_comp_brand,
                    COUNT(CASE WHEN comp_series_name IS NULL OR comp_series_name = '' THEN 1 END) as null_comp_series_name,
                    COUNT(CASE WHEN expected_release IS NULL OR expected_release = '' THEN 1 END) as null_expected_release,
                    COUNT(CASE WHEN comment IS NULL OR comment = '' THEN 1 END) as null_comment,
                    COUNT(CASE WHEN calender_week IS NULL OR calender_week = '' THEN 1 END) as null_calender_week,
                    COUNT(CASE WHEN created_at IS NULL THEN 1 END) as null_created_at,
                    COUNT(CASE WHEN batch_id IS NULL OR batch_id = '' THEN 1 END) as null_batch_id,
                    COUNT(CASE WHEN category IS NULL OR category = '' THEN 1 END) as null_category
                FROM market_comp_product
                WHERE DATE(created_at) = %s
            """, (target_date,))
            market_comp_product_null_row = cursor.fetchone()
            market_comp_product_total = market_comp_product_null_row[0] if market_comp_product_null_row else 0
            market_comp_product_null_issues = sum(v or 0 for v in market_comp_product_null_row[1:11]) if market_comp_product_null_row else 0

            # market_comp_event NULL 검증
            cursor.execute("""
                SELECT
                    COUNT(*) as total,
                    COUNT(CASE WHEN country IS NULL OR country = '' THEN 1 END) as null_country,
                    COUNT(CASE WHEN comp_brand IS NULL OR comp_brand = '' THEN 1 END) as null_comp_brand,
                    COUNT(CASE WHEN comp_sku_name IS NULL OR comp_sku_name = '' THEN 1 END) as null_comp_sku_name,
                    COUNT(CASE WHEN calender_week IS NULL OR calender_week = '' THEN 1 END) as null_calender_week,
                    COUNT(CASE WHEN created_at IS NULL THEN 1 END) as null_created_at,
                    COUNT(CASE WHEN batch_id IS NULL OR batch_id = '' THEN 1 END) as null_batch_id,
                    COUNT(CASE WHEN category IS NULL OR category = '' THEN 1 END) as null_category
                FROM market_comp_event
                WHERE DATE(created_at) = %s
            """, (target_date,))
            market_comp_event_null_row = cursor.fetchone()
            market_comp_event_total = market_comp_event_null_row[0] if market_comp_event_null_row else 0
            market_comp_event_null_issues = sum(v or 0 for v in market_comp_event_null_row[1:8]) if market_comp_event_null_row else 0

            market_total_records = market_trend_total + market_comp_product_total + market_comp_event_total
            market_total_null_issues = market_trend_null_issues + market_comp_product_null_issues + market_comp_event_null_issues

            market_null_retailers = [
                {
                    'retailer': 'Trend',
                    'total': market_trend_total,
                    'records_with_null': market_trend_null_issues,
                    'status': get_status(market_trend_null_issues),
                    'fields_detail': {
                        'keyword': market_trend_null_row[1] if market_trend_null_row else 0,
                        'total_article_number': market_trend_null_row[2] if market_trend_null_row else 0,
                        'calendar_week': market_trend_null_row[3] if market_trend_null_row else 0,
                        'crawl_at_local_time': market_trend_null_row[4] if market_trend_null_row else 0
                    }
                },
                {
                    'retailer': 'Comp Product',
                    'total': market_comp_product_total,
                    'records_with_null': market_comp_product_null_issues,
                    'status': get_status(market_comp_product_null_issues),
                    'fields_detail': {
                        'country': market_comp_product_null_row[1] if market_comp_product_null_row else 0,
                        'samsung_series_name': market_comp_product_null_row[2] if market_comp_product_null_row else 0,
                        'comp_brand': market_comp_product_null_row[3] if market_comp_product_null_row else 0,
                        'comp_series_name': market_comp_product_null_row[4] if market_comp_product_null_row else 0,
                        'expected_release': market_comp_product_null_row[5] if market_comp_product_null_row else 0,
                        'comment': market_comp_product_null_row[6] if market_comp_product_null_row else 0,
                        'calender_week': market_comp_product_null_row[7] if market_comp_product_null_row else 0,
                        'created_at': market_comp_product_null_row[8] if market_comp_product_null_row else 0,
                        'batch_id': market_comp_product_null_row[9] if market_comp_product_null_row else 0,
                        'category': market_comp_product_null_row[10] if market_comp_product_null_row else 0
                    }
                },
                {
                    'retailer': 'Comp Event',
                    'total': market_comp_event_total,
                    'records_with_null': market_comp_event_null_issues,
                    'status': get_status(market_comp_event_null_issues),
                    'fields_detail': {
                        'country': market_comp_event_null_row[1] if market_comp_event_null_row else 0,
                        'comp_brand': market_comp_event_null_row[2] if market_comp_event_null_row else 0,
                        'comp_sku_name': market_comp_event_null_row[3] if market_comp_event_null_row else 0,
                        'calender_week': market_comp_event_null_row[4] if market_comp_event_null_row else 0,
                        'created_at': market_comp_event_null_row[5] if market_comp_event_null_row else 0,
                        'batch_id': market_comp_event_null_row[6] if market_comp_event_null_row else 0,
                        'category': market_comp_event_null_row[7] if market_comp_event_null_row else 0
                    }
                }
            ]

            # OpenAI Forecast NULL 검증 - Market 안에 포함
            try:
                cursor.execute("""
                    SELECT
                        COUNT(*) as total,
                        COUNT(CASE WHEN product_name IS NULL OR product_name = '' THEN 1 END) as null_product_name,
                        COUNT(CASE WHEN event IS NULL OR event = '' THEN 1 END) as null_event,
                        COUNT(CASE WHEN metric_type IS NULL OR metric_type = '' THEN 1 END) as null_metric_type,
                        COUNT(CASE WHEN event_offset IS NULL THEN 1 END) as null_event_offset,
                        COUNT(CASE WHEN event_value IS NULL THEN 1 END) as null_event_value,
                        COUNT(CASE WHEN comment IS NULL OR comment = '' THEN 1 END) as null_comment,
                        COUNT(CASE WHEN week IS NULL OR week = '' THEN 1 END) as null_week,
                        COUNT(CASE WHEN crawled_at IS NULL THEN 1 END) as null_crawled_at
                    FROM openai_forecast_results
                    WHERE DATE(crawled_at) = %s
                """, (target_date,))
                forecast_null_row = cursor.fetchone()
                forecast_total = forecast_null_row[0] if forecast_null_row else 0
                forecast_null_issues = sum(v or 0 for v in forecast_null_row[1:9]) if forecast_null_row else 0

                market_null_retailers.append({
                    'retailer': 'Forecast',
                    'total': forecast_total,
                    'records_with_null': forecast_null_issues,
                    'status': get_status(forecast_null_issues),
                    'fields_detail': {
                        'product_name': forecast_null_row[1] if forecast_null_row else 0,
                        'event': forecast_null_row[2] if forecast_null_row else 0,
                        'metric_type': forecast_null_row[3] if forecast_null_row else 0,
                        'event_offset': forecast_null_row[4] if forecast_null_row else 0,
                        'event_value': forecast_null_row[5] if forecast_null_row else 0,
                        'comment': forecast_null_row[6] if forecast_null_row else 0,
                        'week': forecast_null_row[7] if forecast_null_row else 0,
                        'crawled_at': forecast_null_row[8] if forecast_null_row else 0
                    }
                })
                market_total_records += forecast_total
                market_total_null_issues += forecast_null_issues
            except Exception as e:
                # openai_forecast_results 테이블이 없거나 오류 발생 시 무시
                pass

            null_validation['tables'].append({
                'table': 'market',
                'table_name': 'Market',
                'total_records': market_total_records,
                'total_issues': market_total_null_issues,
                'status': get_status(market_total_null_issues),
                'retailers': market_null_retailers,
                'fields': ['keyword', 'total_article_number', 'calendar_week', 'crawl_at_local_time', 'country', 'samsung_series_name', 'comp_brand', 'comp_series_name', 'expected_release', 'comment', 'calender_week', 'created_at', 'batch_id', 'category', 'comp_sku_name', 'product_name', 'event', 'metric_type', 'event_offset', 'event_value', 'week', 'crawled_at']
            })
            total_null_issues += market_total_null_issues
        except Exception as e:
            # Market 테이블이 없거나 오류 발생 시 무시
            pass

        null_validation['total_issues'] = total_null_issues
        null_validation['status'] = get_status(total_null_issues)
        results['validation_types'].append(null_validation)

        # ============================================================
        # 2. 형식 검증 (데이터 포맷 오류) - 리테일러별 검증
        # ============================================================
        format_validation = {
            'type': 'format',
            'type_name': '형식 검증',
            'type_name_en': 'Format Validation',
            'description': '데이터 형식 및 패턴 검증',
            'icon': '📋',
            'tables': []
        }

        # tv_item_mst에서 유효한 item 목록 조회 (TV Retail 참조 무결성 검증용)
        cursor.execute("SELECT DISTINCT item FROM tv_item_mst")
        tv_valid_items = set(row[0] for row in cursor.fetchall())

        # TV Retail 형식 검증 - 리테일러별 전체 필드 검증
        cursor.execute("""
            SELECT
                account_name, id, item, page_type, product_url,
                main_rank, bsr_rank, final_sku_price, original_sku_price,
                count_of_reviews, star_rating, count_of_star_ratings,
                detailed_review_content,
                number_of_units_purchased_past_month, available_quantity_for_purchase,
                sku_popularity, retailer_membership_discounts,
                rank_1, rank_2, summarized_review_content,
                savings, offer, retailer_sku_name_similar, recommendation_intent,
                number_of_ppl_purchased_yesterday, number_of_ppl_added_to_carts, discount_type
            FROM tv_retail_com
            WHERE DATE(crawl_datetime::timestamp) = %s
            LIMIT 10000
        """, (target_date,))

        tv_format_rows = cursor.fetchall()
        tv_format_errors = []
        tv_format_by_retailer = {'Amazon': 0, 'Bestbuy': 0, 'Walmart': 0}
        tv_format_total_by_retailer = {'Amazon': 0, 'Bestbuy': 0, 'Walmart': 0}

        # 전체 필드 목록
        all_fields = [
            'item', 'page_type', 'product_url', 'main_rank', 'bsr_rank',
            'final_sku_price', 'original_sku_price',
            'count_of_reviews', 'star_rating', 'count_of_star_ratings',
            'detailed_review_content',
            'number_of_units_purchased_past_month', 'available_quantity_for_purchase',
            'sku_popularity', 'retailer_membership_discounts',
            'rank_1', 'rank_2', 'summarized_review_content',
            'savings', 'offer', 'retailer_sku_name_similar', 'recommendation_intent',
            'number_of_ppl_purchased_yesterday', 'number_of_ppl_added_to_carts', 'discount_type'
        ]

        for row in tv_format_rows:
            account_name = row[0] or 'Unknown'
            item_value = row[2]
            errors = []

            # 리테일러별 총 레코드 수 카운트
            if account_name in tv_format_total_by_retailer:
                tv_format_total_by_retailer[account_name] += 1
            else:
                tv_format_total_by_retailer[account_name] = 1

            # row[2]부터 시작 (row[0]=account_name, row[1]=id)
            values = list(row[2:])

            for field, value in zip(all_fields, values):
                error = validate_tv_field(field, value, account_name)
                if error:
                    errors.append({'field': field, 'value': str(value)[:30] if value else '', 'error': error})

            # 크로스 필드 검증 추가
            row_data = dict(zip(all_fields, values))
            cross_errors = validate_cross_field(row_data, account_name)
            errors.extend(cross_errors)

            # 참조 무결성 검증: item이 tv_item_mst에 존재하는지
            if item_value and item_value not in tv_valid_items:
                errors.append({
                    'field': 'item (참조 무결성)',
                    'value': str(item_value)[:30],
                    'error': f'tv_item_mst에 등록되지 않은 item: {item_value}'
                })

            if errors:
                tv_format_errors.append({
                    'id': row[1],
                    'account_name': account_name,
                    'item': row[2],
                    'errors': errors[:5]
                })
                if account_name in tv_format_by_retailer:
                    tv_format_by_retailer[account_name] += len(errors)
                else:
                    tv_format_by_retailer[account_name] = len(errors)

        tv_format_retailers = []
        tv_format_issue_total = 0
        for retailer, count in tv_format_by_retailer.items():
            tv_format_retailers.append({
                'retailer': retailer,
                'total': tv_format_total_by_retailer.get(retailer, 0),
                'issue_count': count,
                'status': get_status(count)
            })
            tv_format_issue_total += count

        format_validation['tables'].append({
            'table': 'tv_retail',
            'table_name': 'TV Retail',
            'total_checked': len(tv_format_rows),
            'total_issues': tv_format_issue_total,
            'status': get_status(tv_format_issue_total),
            'retailers': tv_format_retailers,
            'sample_errors': tv_format_errors[:30]
        })
        total_format_issues += tv_format_issue_total

        # hhp_item_mst에서 유효한 item 목록 조회 (HHP Retail 참조 무결성 검증용)
        cursor.execute("SELECT DISTINCT item FROM hhp_item_mst")
        hhp_valid_items = set(row[0] for row in cursor.fetchall())

        # HHP Retail 형식 검증 - 리테일러별 전체 필드 검증 (HHP 전용 필드 포함)
        cursor.execute("""
            SELECT
                account_name, id, item, page_type, product_url,
                main_rank, bsr_rank, trend_rank, final_sku_price, original_sku_price,
                count_of_reviews, star_rating, count_of_star_ratings,
                detailed_review_content, trade_in, sku_status,
                number_of_units_purchased_past_month, available_quantity_for_purchase,
                sku_popularity, retailer_membership_discounts,
                rank_1, rank_2, summarized_review_content,
                savings, offer, retailer_sku_name_similar, recommendation_intent,
                number_of_ppl_purchased_yesterday, number_of_ppl_added_to_carts, discount_type
            FROM hhp_retail_com
            WHERE DATE(crawl_strdatetime::timestamp) = %s
            LIMIT 10000
        """, (target_date,))

        hhp_format_rows = cursor.fetchall()
        hhp_format_errors = []
        hhp_format_by_retailer = {'Amazon': 0, 'Bestbuy': 0, 'Walmart': 0}
        hhp_format_total_by_retailer = {'Amazon': 0, 'Bestbuy': 0, 'Walmart': 0}

        # HHP 전용 필드 목록 (trend_rank, trade_in, sku_status 포함 - 쿼리 순서와 일치)
        hhp_fields = [
            'item', 'page_type', 'product_url', 'main_rank', 'bsr_rank', 'trend_rank',
            'final_sku_price', 'original_sku_price',
            'count_of_reviews', 'star_rating', 'count_of_star_ratings',
            'detailed_review_content', 'trade_in', 'sku_status',
            'number_of_units_purchased_past_month', 'available_quantity_for_purchase',
            'sku_popularity', 'retailer_membership_discounts',
            'rank_1', 'rank_2', 'summarized_review_content',
            'savings', 'offer', 'retailer_sku_name_similar', 'recommendation_intent',
            'number_of_ppl_purchased_yesterday', 'number_of_ppl_added_to_carts', 'discount_type'
        ]

        for row in hhp_format_rows:
            account_name = row[0] or 'Unknown'
            item_value = row[2]
            errors = []

            # 리테일러별 총 레코드 수 카운트
            if account_name in hhp_format_total_by_retailer:
                hhp_format_total_by_retailer[account_name] += 1
            else:
                hhp_format_total_by_retailer[account_name] = 1

            # row[2]부터 시작 (row[0]=account_name, row[1]=id)
            values = list(row[2:])

            for field, value in zip(hhp_fields, values):
                error = validate_hhp_field(field, value, account_name)
                if error:
                    errors.append({'field': field, 'value': str(value)[:30] if value else '', 'error': error})

            # 크로스 필드 검증 추가
            row_data = dict(zip(hhp_fields, values))
            cross_errors = validate_cross_field(row_data, account_name)
            errors.extend(cross_errors)

            # 참조 무결성 검증: item이 hhp_item_mst에 존재하는지
            if item_value and item_value not in hhp_valid_items:
                errors.append({
                    'field': 'item (참조 무결성)',
                    'value': str(item_value)[:30],
                    'error': f'hhp_item_mst에 등록되지 않은 item: {item_value}'
                })

            if errors:
                hhp_format_errors.append({
                    'id': row[1],
                    'account_name': account_name,
                    'item': row[2],
                    'errors': errors[:5]
                })
                if account_name in hhp_format_by_retailer:
                    hhp_format_by_retailer[account_name] += len(errors)
                else:
                    hhp_format_by_retailer[account_name] = len(errors)

        hhp_format_retailers = []
        hhp_format_issue_total = 0
        for retailer, count in hhp_format_by_retailer.items():
            hhp_format_retailers.append({
                'retailer': retailer,
                'total': hhp_format_total_by_retailer.get(retailer, 0),
                'issue_count': count,
                'status': get_status(count)
            })
            hhp_format_issue_total += count

        format_validation['tables'].append({
            'table': 'hhp_retail',
            'table_name': 'HHP Retail',
            'total_checked': len(hhp_format_rows),
            'total_issues': hhp_format_issue_total,
            'status': get_status(hhp_format_issue_total),
            'retailers': hhp_format_retailers,
            'sample_errors': hhp_format_errors[:30]
        })
        total_format_issues += hhp_format_issue_total

        # YouTube 형식 검증 (Logs, Videos, Comments 통합)
        # Logs 형식 검증
        cursor.execute("""
            SELECT
                COUNT(*) as total,
                COUNT(CASE WHEN l.keyword IS NOT NULL AND l.keyword NOT IN (SELECT keyword FROM youtube_keywords WHERE status = 'active') THEN 1 END) as invalid_keyword,
                COUNT(CASE WHEN l.status IS NOT NULL AND l.status NOT IN ('failed', 'completed') THEN 1 END) as invalid_status,
                COUNT(CASE WHEN videos_collected IS NOT NULL AND videos_collected < 0 THEN 1 END) as invalid_videos_collected,
                COUNT(CASE WHEN comments_collected IS NOT NULL AND comments_collected < 0 THEN 1 END) as invalid_comments_collected
            FROM youtube_collection_logs l
            WHERE DATE(l.started_at) = %s
        """, (target_date,))
        yt_log_format_row = cursor.fetchone()
        # None 값을 0으로 변환하여 합산
        yt_log_format_issues = sum(v or 0 for v in yt_log_format_row[1:5]) if yt_log_format_row else 0

        # Videos 형식 검증
        cursor.execute("""
            SELECT
                COUNT(*) as total,
                COUNT(CASE WHEN v.keyword IS NOT NULL AND v.keyword NOT IN (SELECT keyword FROM youtube_keywords WHERE status = 'active') THEN 1 END) as invalid_keyword,
                COUNT(CASE WHEN published_at IS NOT NULL AND created_at IS NOT NULL AND published_at > created_at THEN 1 END) as invalid_published_at,
                COUNT(CASE WHEN channel_custom_url IS NOT NULL AND channel_custom_url != '' AND LEFT(channel_custom_url, 1) != '@' THEN 1 END) as invalid_channel_url,
                COUNT(CASE WHEN channel_subscriber_count IS NOT NULL AND channel_subscriber_count < 0 THEN 1 END) as invalid_subscriber_count,
                COUNT(CASE WHEN channel_video_count IS NOT NULL AND channel_video_count < 0 THEN 1 END) as invalid_video_count,
                COUNT(CASE WHEN view_count IS NOT NULL AND view_count < 0 THEN 1 END) as invalid_view_count,
                COUNT(CASE WHEN like_count IS NOT NULL AND like_count < 0 THEN 1 END) as invalid_like_count,
                COUNT(CASE WHEN comment_count IS NOT NULL AND comment_count < 0 THEN 1 END) as invalid_comment_count,
                COUNT(CASE WHEN category IS NOT NULL AND category NOT IN ('TV', 'HHP') THEN 1 END) as invalid_category,
                COUNT(CASE WHEN engagement_rate IS NOT NULL AND engagement_rate < 2.0 THEN 1 END) as invalid_engagement_rate,
                COUNT(CASE WHEN product_sentiment_score IS NOT NULL AND (product_sentiment_score < -5.0 OR product_sentiment_score > 5.0) THEN 1 END) as invalid_sentiment_score
            FROM youtube_videos v
            WHERE DATE(created_at) = %s
        """, (target_date,))
        yt_video_format_row = cursor.fetchone()
        # None 값을 0으로 변환하여 합산
        yt_video_format_issues = sum(v or 0 for v in yt_video_format_row[1:12]) if yt_video_format_row else 0

        # Comments 형식 검증
        cursor.execute("""
            SELECT
                COUNT(*) as total,
                COUNT(CASE WHEN c.video_id IS NOT NULL AND c.video_id NOT IN (SELECT video_id FROM youtube_videos) THEN 1 END) as invalid_video_id,
                COUNT(CASE WHEN comment_type IS NOT NULL AND comment_type NOT IN ('top_level', 'reply') THEN 1 END) as invalid_comment_type,
                COUNT(CASE WHEN parent_comment_id IS NOT NULL AND parent_comment_id != '' AND comment_type = 'top_level' THEN 1 END) as invalid_parent_comment,
                COUNT(CASE WHEN like_count IS NOT NULL AND like_count < 0 THEN 1 END) as invalid_like_count,
                COUNT(CASE WHEN reply_count IS NOT NULL AND reply_count < 0 THEN 1 END) as invalid_reply_count,
                COUNT(CASE WHEN published_at IS NOT NULL AND created_at IS NOT NULL AND published_at > created_at THEN 1 END) as invalid_published_at
            FROM youtube_comments c
            WHERE DATE(created_at) = %s
        """, (target_date,))
        yt_comment_format_row = cursor.fetchone()
        # None 값을 0으로 변환하여 합산
        yt_comment_format_issues = sum(v or 0 for v in yt_comment_format_row[1:7]) if yt_comment_format_row else 0

        # YouTube 통합 (리테일러 형태로) - 순서: Logs, Videos, Comments
        yt_total_format_issues = yt_log_format_issues + yt_video_format_issues + yt_comment_format_issues

        # 안전한 인덱스 접근 헬퍼 함수
        def safe_get(row, idx, default=0):
            if row is None or idx >= len(row):
                return default
            return row[idx] if row[idx] is not None else default

        yt_total_format_checked = safe_get(yt_log_format_row, 0) + safe_get(yt_video_format_row, 0) + safe_get(yt_comment_format_row, 0)

        youtube_format_retailers = [
            {
                'retailer': 'Logs',
                'total': safe_get(yt_log_format_row, 0),
                'issue_count': yt_log_format_issues,
                'status': get_status(yt_log_format_issues),
                'fields_detail': {
                    'keyword 비활성': safe_get(yt_log_format_row, 1),
                    'status 값 오류': safe_get(yt_log_format_row, 2),
                    'videos_collected 음수': safe_get(yt_log_format_row, 3),
                    'comments_collected 음수': safe_get(yt_log_format_row, 4)
                }
            },
            {
                'retailer': 'Videos',
                'total': safe_get(yt_video_format_row, 0),
                'issue_count': yt_video_format_issues,
                'status': get_status(yt_video_format_issues),
                'fields_detail': {
                    'keyword 비활성': safe_get(yt_video_format_row, 1),
                    'published_at > created_at': safe_get(yt_video_format_row, 2),
                    'channel_url @누락': safe_get(yt_video_format_row, 3),
                    'subscriber_count 음수': safe_get(yt_video_format_row, 4),
                    'video_count 음수': safe_get(yt_video_format_row, 5),
                    'view_count 음수': safe_get(yt_video_format_row, 6),
                    'like_count 음수': safe_get(yt_video_format_row, 7),
                    'comment_count 음수': safe_get(yt_video_format_row, 8),
                    'category 오류': safe_get(yt_video_format_row, 9),
                    'engagement_rate < 2.0': safe_get(yt_video_format_row, 10),
                    'sentiment 범위 오류': safe_get(yt_video_format_row, 11)
                }
            },
            {
                'retailer': 'Comments',
                'total': safe_get(yt_comment_format_row, 0),
                'issue_count': yt_comment_format_issues,
                'status': get_status(yt_comment_format_issues),
                'fields_detail': {
                    'video_id 참조 오류': safe_get(yt_comment_format_row, 1),
                    'comment_type 오류': safe_get(yt_comment_format_row, 2),
                    'parent_comment 오류': safe_get(yt_comment_format_row, 3),
                    'like_count 음수': safe_get(yt_comment_format_row, 4),
                    'reply_count 음수': safe_get(yt_comment_format_row, 5),
                    'published_at > created_at': safe_get(yt_comment_format_row, 6)
                }
            }
        ]

        format_validation['tables'].append({
            'table': 'youtube',
            'table_name': 'YouTube',
            'total_checked': yt_total_format_checked,
            'total_issues': yt_total_format_issues,
            'status': get_status(yt_total_format_issues),
            'retailers': youtube_format_retailers
        })
        total_format_issues += yt_total_format_issues

        # Market 형식 검증 (Trend, Comp Product, Comp Event)
        try:
            # market_trend 형식 검증
            cursor.execute("""
                SELECT
                    COUNT(*) as total,
                    COUNT(CASE WHEN keyword IS NOT NULL AND keyword != '' AND keyword NOT IN (SELECT keyword FROM market_mst WHERE analysis_type = 'trend') THEN 1 END) as invalid_keyword,
                    COUNT(CASE WHEN total_article_number IS NOT NULL AND total_article_number < 0 THEN 1 END) as invalid_total_article_number,
                    COUNT(CASE WHEN calendar_week IS NOT NULL AND calendar_week != '' AND calendar_week !~ '^W([1-9]|[1-4][0-9]|5[0-2])$' THEN 1 END) as invalid_calendar_week
                FROM market_trend
                WHERE DATE(crawl_at_local_time) = %s
            """, (target_date,))
            market_trend_format_row = cursor.fetchone()
            market_trend_format_issues = sum(v or 0 for v in market_trend_format_row[1:4]) if market_trend_format_row else 0

            # market_comp_product 형식 검증
            cursor.execute("""
                SELECT
                    COUNT(*) as total,
                    COUNT(CASE WHEN samsung_series_name IS NOT NULL AND samsung_series_name != '' AND samsung_series_name NOT IN (SELECT keyword FROM market_mst WHERE analysis_type = 'competitor' AND content_type = 'samsung') THEN 1 END) as invalid_samsung_series,
                    COUNT(CASE WHEN comp_brand IS NOT NULL AND comp_brand != '' AND comp_brand NOT IN (SELECT keyword FROM market_mst WHERE analysis_type = 'competitor' AND content_type = 'comp') THEN 1 END) as invalid_comp_brand,
                    COUNT(CASE WHEN calender_week IS NOT NULL AND calender_week != '' AND LOWER(calender_week) !~ '^w([1-9]|[1-4][0-9]|5[0-2])$' THEN 1 END) as invalid_calender_week,
                    COUNT(CASE WHEN category IS NOT NULL AND category != '' AND category NOT IN ('TV', 'HHP') THEN 1 END) as invalid_category
                FROM market_comp_product
                WHERE DATE(created_at) = %s
            """, (target_date,))
            market_comp_product_format_row = cursor.fetchone()
            market_comp_product_format_issues = sum(v or 0 for v in market_comp_product_format_row[1:5]) if market_comp_product_format_row else 0

            # market_comp_event 형식 검증 - 최신 배치 기준 comp_brand, comp_series_name 검증
            cursor.execute("""
                WITH latest_batch AS (
                    SELECT comp_brand, comp_series_name FROM market_comp_product
                    WHERE batch_id = (SELECT MAX(batch_id) FROM market_comp_product WHERE DATE(created_at) <= %s)
                )
                SELECT
                    COUNT(*) as total,
                    COUNT(CASE WHEN e.comp_brand IS NOT NULL AND e.comp_brand != '' AND e.comp_brand NOT IN (SELECT comp_brand FROM latest_batch) THEN 1 END) as invalid_comp_brand,
                    COUNT(CASE WHEN e.comp_sku_name IS NOT NULL AND e.comp_sku_name != '' AND e.comp_sku_name NOT IN (SELECT comp_series_name FROM latest_batch) THEN 1 END) as invalid_comp_sku_name,
                    COUNT(CASE WHEN e.calender_week IS NOT NULL AND e.calender_week != '' AND LOWER(e.calender_week) !~ '^w([1-9]|[1-4][0-9]|5[0-2])$' THEN 1 END) as invalid_calender_week,
                    COUNT(CASE WHEN e.category IS NOT NULL AND e.category != '' AND e.category NOT IN ('TV', 'HHP') THEN 1 END) as invalid_category
                FROM market_comp_event e
                WHERE DATE(e.created_at) = %s
            """, (target_date, target_date))
            market_comp_event_format_row = cursor.fetchone()
            market_comp_event_format_issues = sum(v or 0 for v in market_comp_event_format_row[1:5]) if market_comp_event_format_row else 0

            # openai_forecast_results 형식 검증
            cursor.execute("""
                SELECT
                    COUNT(*) as total,
                    COUNT(CASE WHEN product_name IS NOT NULL AND product_name != '' AND product_name NOT IN (SELECT product_name FROM openai_keywords WHERE is_active = true) THEN 1 END) as invalid_product_name,
                    COUNT(CASE WHEN event IS NOT NULL AND event != '' AND REPLACE(LOWER(event), ' ', '_') NOT IN (SELECT LOWER(REPLACE(event_name, ' ', '_')) FROM openai_event_mst WHERE is_active = true) THEN 1 END) as invalid_event,
                    COUNT(CASE WHEN metric_type IS NOT NULL AND metric_type != '' AND metric_type != 'Forecasted_NA_sales_change' THEN 1 END) as invalid_metric_type,
                    COUNT(CASE WHEN event_offset IS NOT NULL AND (event_offset < 0 OR event_offset > 9) THEN 1 END) as invalid_event_offset,
                    COUNT(CASE WHEN event_value IS NOT NULL AND event_value::text !~ '^-?[0-9]+\.?[0-9]*$' THEN 1 END) as invalid_event_value,
                    COUNT(CASE WHEN week IS NOT NULL AND week != '' AND week !~ '^w[0-9]{1,2}$' THEN 1 END) as invalid_week,
                    COUNT(CASE WHEN crawled_at IS NOT NULL AND crawled_at::text !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$' THEN 1 END) as invalid_crawled_at
                FROM openai_forecast_results
                WHERE DATE(crawled_at) = %s
            """, (target_date,))
            forecast_format_row = cursor.fetchone()
            forecast_format_issues = sum(v or 0 for v in forecast_format_row[1:8]) if forecast_format_row else 0

            market_total_format_checked = (market_trend_format_row[0] if market_trend_format_row else 0) + \
                                           (market_comp_product_format_row[0] if market_comp_product_format_row else 0) + \
                                           (market_comp_event_format_row[0] if market_comp_event_format_row else 0) + \
                                           (forecast_format_row[0] if forecast_format_row else 0)
            market_total_format_issues = market_trend_format_issues + market_comp_product_format_issues + market_comp_event_format_issues + forecast_format_issues

            market_format_retailers = [
                {
                    'retailer': 'Trend',
                    'total': market_trend_format_row[0] if market_trend_format_row else 0,
                    'issue_count': market_trend_format_issues,
                    'status': get_status(market_trend_format_issues),
                    'fields_detail': {
                        'keyword 미등록': market_trend_format_row[1] if market_trend_format_row else 0,
                        'total_article_number 음수': market_trend_format_row[2] if market_trend_format_row else 0,
                        'calendar_week 형식 오류': market_trend_format_row[3] if market_trend_format_row else 0
                    }
                },
                {
                    'retailer': 'Comp Product',
                    'total': market_comp_product_format_row[0] if market_comp_product_format_row else 0,
                    'issue_count': market_comp_product_format_issues,
                    'status': get_status(market_comp_product_format_issues),
                    'fields_detail': {
                        'samsung_series_name 미등록': market_comp_product_format_row[1] if market_comp_product_format_row else 0,
                        'comp_brand 미등록': market_comp_product_format_row[2] if market_comp_product_format_row else 0,
                        'calender_week 형식 오류': market_comp_product_format_row[3] if market_comp_product_format_row else 0,
                        'category 값 오류': market_comp_product_format_row[4] if market_comp_product_format_row else 0
                    }
                },
                {
                    'retailer': 'Comp Event',
                    'total': market_comp_event_format_row[0] if market_comp_event_format_row else 0,
                    'issue_count': market_comp_event_format_issues,
                    'status': get_status(market_comp_event_format_issues),
                    'fields_detail': {
                        'comp_brand 미등록': market_comp_event_format_row[1] if market_comp_event_format_row else 0,
                        'comp_sku_name 미등록': market_comp_event_format_row[2] if market_comp_event_format_row else 0,
                        'calender_week 형식 오류': market_comp_event_format_row[3] if market_comp_event_format_row else 0,
                        'category 값 오류': market_comp_event_format_row[4] if market_comp_event_format_row else 0
                    }
                },
                {
                    'retailer': 'Forecast',
                    'total': forecast_format_row[0] if forecast_format_row else 0,
                    'issue_count': forecast_format_issues,
                    'status': get_status(forecast_format_issues),
                    'fields_detail': {
                        'product_name 미등록': forecast_format_row[1] if forecast_format_row else 0,
                        'event 미등록': forecast_format_row[2] if forecast_format_row else 0,
                        'metric_type 값 오류': forecast_format_row[3] if forecast_format_row else 0,
                        'event_offset 범위 오류': forecast_format_row[4] if forecast_format_row else 0,
                        'event_value 형식 오류': forecast_format_row[5] if forecast_format_row else 0,
                        'week 형식 오류': forecast_format_row[6] if forecast_format_row else 0,
                        'crawled_at 형식 오류': forecast_format_row[7] if forecast_format_row else 0
                    }
                }
            ]

            format_validation['tables'].append({
                'table': 'market',
                'table_name': 'Market',
                'total_checked': market_total_format_checked,
                'total_issues': market_total_format_issues,
                'status': get_status(market_total_format_issues),
                'retailers': market_format_retailers
            })
            total_format_issues += market_total_format_issues
        except Exception as e:
            pass  # Market 테이블이 없거나 컬럼이 다른 경우 무시

        format_validation['total_issues'] = total_format_issues
        format_validation['status'] = get_status(total_format_issues)
        results['validation_types'].append(format_validation)

        # ============================================================
        # 3. 중복 검증 (동일 상품 중복 수집)
        # ============================================================
        anomaly_validation = {
            'type': 'duplicate',
            'type_name': '중복 검증',
            'type_name_en': 'Duplicate Validation',
            'description': '동일 시간대 동일 상품 중복 수집 탐지',
            'icon': '🔄',
            'tables': []
        }

        # TV Retail 이상치: 총 레코드 수 조회
        cursor.execute("""
            SELECT COUNT(*) FROM tv_retail_com
            WHERE DATE(crawl_datetime::timestamp) = %s
        """, (target_date,))
        tv_total_records = cursor.fetchone()[0] or 0

        # TV Retail 이상치: 중복 데이터
        cursor.execute("""
            SELECT account_name, COUNT(*) as dup_groups FROM (
                SELECT item, account_name,
                       CASE WHEN EXTRACT(HOUR FROM crawl_datetime::timestamp) < 12 THEN '오전' ELSE '오후' END as period
                FROM tv_retail_com
                WHERE DATE(crawl_datetime::timestamp) = %s
                GROUP BY item, account_name, period
                HAVING COUNT(*) > 1
            ) sub
            GROUP BY account_name
            ORDER BY account_name
        """, (target_date,))

        tv_dup_rows = cursor.fetchall()
        tv_dup_dict = {row[0]: row[1] for row in tv_dup_rows}
        tv_dup_retailers = []
        tv_dup_total = 0
        # 모든 retailer 포함 (중복 0건이어도 표시)
        for retailer_name in ['Amazon', 'Bestbuy', 'Walmart']:
            dup_count = tv_dup_dict.get(retailer_name, 0)
            tv_dup_retailers.append({
                'retailer': retailer_name,
                'duplicate_groups': dup_count,
                'status': get_status(dup_count)
            })
            tv_dup_total += dup_count

        # TV Retail 이상치: 가격 이상 (음수 또는 비정상적 고가)
        cursor.execute("""
            SELECT COUNT(*) FROM tv_retail_com
            WHERE DATE(crawl_datetime::timestamp) = %s
            AND final_sku_price ~ '^\$[\d,]+\.?\d*$'
            AND (
                CAST(REPLACE(REPLACE(final_sku_price, '$', ''), ',', '') AS DECIMAL) < 0
                OR CAST(REPLACE(REPLACE(final_sku_price, '$', ''), ',', '') AS DECIMAL) > 50000
            )
        """, (target_date,))
        tv_price_anomaly = cursor.fetchone()[0] or 0

        anomaly_validation['tables'].append({
            'table': 'tv_retail',
            'table_name': 'TV Retail',
            'total_records': tv_total_records,
            'total_issues': tv_dup_total + tv_price_anomaly,
            'duplicate_groups': tv_dup_total,
            'price_anomalies': tv_price_anomaly,
            'status': get_status(tv_dup_total + tv_price_anomaly),
            'retailers': tv_dup_retailers
        })
        total_anomaly_issues += tv_dup_total + tv_price_anomaly

        # HHP Retail 이상치: 총 레코드 수 조회
        cursor.execute("""
            SELECT COUNT(*) FROM hhp_retail_com
            WHERE DATE(crawl_strdatetime::timestamp) = %s
        """, (target_date,))
        hhp_total_records = cursor.fetchone()[0] or 0

        # HHP Retail 이상치: 중복 데이터
        cursor.execute("""
            SELECT account_name, COUNT(*) as dup_groups FROM (
                SELECT item, account_name,
                       CASE WHEN EXTRACT(HOUR FROM crawl_strdatetime::timestamp) < 12 THEN '오전' ELSE '오후' END as period
                FROM hhp_retail_com
                WHERE DATE(crawl_strdatetime::timestamp) = %s
                GROUP BY item, account_name, period
                HAVING COUNT(*) > 1
            ) sub
            GROUP BY account_name
            ORDER BY account_name
        """, (target_date,))

        hhp_dup_rows = cursor.fetchall()
        hhp_dup_dict = {row[0]: row[1] for row in hhp_dup_rows}
        hhp_dup_retailers = []
        hhp_dup_total = 0
        # 모든 retailer 포함 (중복 0건이어도 표시)
        for retailer_name in ['Amazon', 'Bestbuy', 'Walmart']:
            dup_count = hhp_dup_dict.get(retailer_name, 0)
            hhp_dup_retailers.append({
                'retailer': retailer_name,
                'duplicate_groups': dup_count,
                'status': get_status(dup_count)
            })
            hhp_dup_total += dup_count

        anomaly_validation['tables'].append({
            'table': 'hhp_retail',
            'table_name': 'HHP Retail',
            'total_records': hhp_total_records,
            'total_issues': hhp_dup_total,
            'duplicate_groups': hhp_dup_total,
            'status': get_status(hhp_dup_total),
            'retailers': hhp_dup_retailers
        })
        total_anomaly_issues += hhp_dup_total

        anomaly_validation['total_issues'] = total_anomaly_issues
        anomaly_validation['status'] = get_status(total_anomaly_issues)
        results['validation_types'].append(anomaly_validation)

        cursor.close()
        conn.close()

        # Summary 계산
        total_issues = total_null_issues + total_format_issues + total_anomaly_issues
        results['summary'] = {
            'total_issues': total_issues,
            'null_issues': total_null_issues,
            'format_issues': total_format_issues,
            'duplicate_issues': total_anomaly_issues,
            'overall_status': 'OK' if total_issues == 0 else ('WARNING' if total_issues <= 30 else 'CRITICAL')
        }

    except Exception as e:
        import traceback
        results['error'] = str(e)
        results['error_detail'] = traceback.format_exc()
        results['summary']['overall_status'] = 'ERROR'
        print(f"[Layer2 DX Error] {e}")
        print(traceback.format_exc())

    return JsonResponse(results)


def null_detail(request):
    """NULL 필드 상세 조회 API"""
    date_str = request.GET.get('date')
    table = request.GET.get('table', 'tv_retail')
    retailer = request.GET.get('retailer')

    if date_str:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    else:
        target_date = (datetime.now() - timedelta(days=1)).date()

    next_date = target_date + timedelta(days=1)

    try:
        conn = get_dx_connection()
        cursor = conn.cursor()

        if table == 'tv_retail':
            query = """
                SELECT id, crawl_datetime, account_name, item, screen_size, final_sku_price,
                       retailer_sku_name, count_of_reviews, star_rating, count_of_star_ratings, product_url
                FROM tv_retail_com
                WHERE crawl_datetime::timestamp >= %s AND crawl_datetime::timestamp < %s
                  AND (item IS NULL OR item = '' OR screen_size IS NULL OR screen_size = ''
                      OR final_sku_price IS NULL OR final_sku_price = ''
                      OR retailer_sku_name IS NULL OR retailer_sku_name = ''
                      OR count_of_reviews IS NULL OR count_of_reviews = ''
                      OR star_rating IS NULL OR star_rating = ''
                      OR count_of_star_ratings IS NULL OR count_of_star_ratings = '')
            """
            params = [str(target_date), str(next_date)]

            if retailer:
                query += " AND account_name = %s"
                params.append(retailer)

            query += " ORDER BY account_name, crawl_datetime LIMIT 200"
            cursor.execute(query, params)

            rows = cursor.fetchall()
            results = []
            for row in rows:
                null_fields = []
                if not row[3]: null_fields.append('item')
                if not row[4]: null_fields.append('screen_size')
                if not row[5]: null_fields.append('final_sku_price')
                if not row[6]: null_fields.append('retailer_sku_name')
                if not row[7]: null_fields.append('count_of_reviews')
                if not row[8]: null_fields.append('star_rating')
                if not row[9]: null_fields.append('count_of_star_ratings')

                results.append({
                    'id': row[0],
                    'crawl_datetime': str(row[1]) if row[1] else None,
                    'account_name': row[2],
                    'item': row[3],
                    'screen_size': row[4],
                    'final_sku_price': row[5],
                    'retailer_sku_name': row[6],
                    'count_of_reviews': row[7],
                    'star_rating': row[8],
                    'count_of_star_ratings': row[9],
                    'product_url': row[10],
                    'null_fields': null_fields
                })

        elif table == 'hhp_retail':
            query = """
                SELECT id, crawl_strdatetime, account_name, item, final_sku_price,
                       retailer_sku_name, count_of_reviews, star_rating, count_of_star_ratings, product_url
                FROM hhp_retail_com
                WHERE crawl_strdatetime::timestamp >= %s AND crawl_strdatetime::timestamp < %s
                  AND (item IS NULL OR item = ''
                      OR final_sku_price IS NULL OR final_sku_price = ''
                      OR retailer_sku_name IS NULL OR retailer_sku_name = ''
                      OR count_of_reviews IS NULL OR count_of_reviews = ''
                      OR star_rating IS NULL OR star_rating = ''
                      OR count_of_star_ratings IS NULL OR count_of_star_ratings = '')
            """
            params = [str(target_date), str(next_date)]

            if retailer:
                query += " AND account_name = %s"
                params.append(retailer)

            query += " ORDER BY account_name, crawl_strdatetime LIMIT 200"
            cursor.execute(query, params)

            rows = cursor.fetchall()
            results = []
            for row in rows:
                null_fields = []
                if not row[3]: null_fields.append('item')
                if not row[4]: null_fields.append('final_sku_price')
                if not row[5]: null_fields.append('retailer_sku_name')
                if not row[6]: null_fields.append('count_of_reviews')
                if not row[7]: null_fields.append('star_rating')
                if not row[8]: null_fields.append('count_of_star_ratings')

                results.append({
                    'id': row[0],
                    'crawl_datetime': str(row[1]) if row[1] else None,
                    'account_name': row[2],
                    'item': row[3],
                    'final_sku_price': row[4],
                    'retailer_sku_name': row[5],
                    'count_of_reviews': row[6],
                    'star_rating': row[7],
                    'count_of_star_ratings': row[8],
                    'product_url': row[9],
                    'null_fields': null_fields
                })

        elif table == 'youtube':
            results = []

            if retailer == 'Logs':
                # youtube_collection_logs NULL 상세
                query = """
                    SELECT id, keyword_id, keyword, status, videos_collected, comments_collected,
                           started_at, completed_at
                    FROM youtube_collection_logs
                    WHERE DATE(started_at) = %s
                      AND (keyword_id IS NULL
                          OR keyword IS NULL OR keyword = ''
                          OR status IS NULL OR status = ''
                          OR videos_collected IS NULL
                          OR comments_collected IS NULL
                          OR started_at IS NULL
                          OR completed_at IS NULL)
                    ORDER BY started_at DESC
                    LIMIT 200
                """
                cursor.execute(query, (target_date,))
                rows = cursor.fetchall()

                for row in rows:
                    null_fields = []
                    if row[1] is None: null_fields.append('keyword_id')
                    if not row[2]: null_fields.append('keyword')
                    if not row[3]: null_fields.append('status')
                    if row[4] is None: null_fields.append('videos_collected')
                    if row[5] is None: null_fields.append('comments_collected')
                    if row[6] is None: null_fields.append('started_at')
                    if row[7] is None: null_fields.append('completed_at')

                    results.append({
                        'id': row[0],
                        'item': row[2] or f'keyword_id: {row[1]}',  # keyword를 item으로 표시
                        'crawl_datetime': str(row[6]) if row[6] else None,
                        'null_fields': null_fields
                    })

            elif retailer == 'Videos':
                # youtube_videos NULL 상세
                query = """
                    SELECT id, video_id, keyword, title, channel_id, channel_title,
                           published_at, created_at
                    FROM youtube_videos
                    WHERE DATE(created_at) = %s
                      AND (video_id IS NULL OR video_id = ''
                          OR keyword IS NULL OR keyword = ''
                          OR title IS NULL OR title = ''
                          OR channel_id IS NULL OR channel_id = ''
                          OR channel_title IS NULL OR channel_title = ''
                          OR published_at IS NULL
                          OR created_at IS NULL)
                    ORDER BY created_at DESC
                    LIMIT 200
                """
                cursor.execute(query, (target_date,))
                rows = cursor.fetchall()

                for row in rows:
                    null_fields = []
                    if not row[1]: null_fields.append('video_id')
                    if not row[2]: null_fields.append('keyword')
                    if not row[3]: null_fields.append('title')
                    if not row[4]: null_fields.append('channel_id')
                    if not row[5]: null_fields.append('channel_title')
                    if row[6] is None: null_fields.append('published_at')
                    if row[7] is None: null_fields.append('created_at')

                    results.append({
                        'id': row[0],
                        'item': row[1] or '-',  # video_id를 item으로 표시
                        'crawl_datetime': str(row[7]) if row[7] else None,
                        'null_fields': null_fields
                    })

            elif retailer == 'Comments':
                # youtube_comments NULL 상세
                query = """
                    SELECT id, video_id, comment_id, author_name, text_original,
                           published_at, created_at
                    FROM youtube_comments
                    WHERE DATE(created_at) = %s
                      AND (video_id IS NULL OR video_id = ''
                          OR comment_id IS NULL OR comment_id = ''
                          OR author_name IS NULL OR author_name = ''
                          OR text_original IS NULL OR text_original = ''
                          OR published_at IS NULL
                          OR created_at IS NULL)
                    ORDER BY created_at DESC
                    LIMIT 200
                """
                cursor.execute(query, (target_date,))
                rows = cursor.fetchall()

                for row in rows:
                    null_fields = []
                    if not row[1]: null_fields.append('video_id')
                    if not row[2]: null_fields.append('comment_id')
                    if not row[3]: null_fields.append('author_name')
                    if not row[4]: null_fields.append('text_original')
                    if row[5] is None: null_fields.append('published_at')
                    if row[6] is None: null_fields.append('created_at')

                    results.append({
                        'id': row[0],
                        'item': row[2] or row[1] or '-',  # comment_id를 item으로 표시
                        'crawl_datetime': str(row[6]) if row[6] else None,
                        'null_fields': null_fields
                    })

        elif table == 'market':
            results = []

            if retailer == 'Trend':
                # market_trend NULL 상세
                query = """
                    SELECT id, keyword, total_article_number, calendar_week, crawl_at_local_time
                    FROM market_trend
                    WHERE DATE(crawl_at_local_time) = %s
                      AND (keyword IS NULL OR keyword = ''
                          OR total_article_number IS NULL
                          OR calendar_week IS NULL OR calendar_week = ''
                          OR crawl_at_local_time IS NULL)
                    ORDER BY crawl_at_local_time DESC
                    LIMIT 200
                """
                cursor.execute(query, (target_date,))
                rows = cursor.fetchall()

                for row in rows:
                    null_fields = []
                    if not row[1]: null_fields.append('keyword')
                    if row[2] is None: null_fields.append('total_article_number')
                    if not row[3]: null_fields.append('calendar_week')
                    if row[4] is None: null_fields.append('crawl_at_local_time')

                    results.append({
                        'id': row[0],
                        'item': row[1] or '-',
                        'crawl_datetime': str(row[4]) if row[4] else None,
                        'null_fields': null_fields
                    })

            elif retailer == 'Comp Product':
                # market_comp_product NULL 상세
                query = """
                    SELECT id, country, samsung_series_name, comp_brand, comp_series_name,
                           expected_release, comment, calender_week, created_at, batch_id, category
                    FROM market_comp_product
                    WHERE DATE(created_at) = %s
                      AND (country IS NULL OR country = ''
                          OR samsung_series_name IS NULL OR samsung_series_name = ''
                          OR comp_brand IS NULL OR comp_brand = ''
                          OR comp_series_name IS NULL OR comp_series_name = ''
                          OR expected_release IS NULL OR expected_release = ''
                          OR comment IS NULL OR comment = ''
                          OR calender_week IS NULL OR calender_week = ''
                          OR created_at IS NULL
                          OR batch_id IS NULL OR batch_id = ''
                          OR category IS NULL OR category = '')
                    ORDER BY created_at DESC
                    LIMIT 200
                """
                cursor.execute(query, (target_date,))
                rows = cursor.fetchall()

                for row in rows:
                    null_fields = []
                    if not row[1]: null_fields.append('country')
                    if not row[2]: null_fields.append('samsung_series_name')
                    if not row[3]: null_fields.append('comp_brand')
                    if not row[4]: null_fields.append('comp_series_name')
                    if not row[5]: null_fields.append('expected_release')
                    if not row[6]: null_fields.append('comment')
                    if not row[7]: null_fields.append('calender_week')
                    if row[8] is None: null_fields.append('created_at')
                    if not row[9]: null_fields.append('batch_id')
                    if not row[10]: null_fields.append('category')

                    results.append({
                        'id': row[0],
                        'item': f"{row[2] or '-'} / {row[3] or '-'}",  # samsung_series_name / comp_brand
                        'crawl_datetime': str(row[8]) if row[8] else None,
                        'null_fields': null_fields
                    })

            elif retailer == 'Comp Event':
                # market_comp_event NULL 상세
                query = """
                    SELECT id, country, comp_brand, comp_sku_name, calender_week, created_at, batch_id, category
                    FROM market_comp_event
                    WHERE DATE(created_at) = %s
                      AND (country IS NULL OR country = ''
                          OR comp_brand IS NULL OR comp_brand = ''
                          OR comp_sku_name IS NULL OR comp_sku_name = ''
                          OR calender_week IS NULL OR calender_week = ''
                          OR created_at IS NULL
                          OR batch_id IS NULL OR batch_id = ''
                          OR category IS NULL OR category = '')
                    ORDER BY created_at DESC
                    LIMIT 200
                """
                cursor.execute(query, (target_date,))
                rows = cursor.fetchall()

                for row in rows:
                    null_fields = []
                    if not row[1]: null_fields.append('country')
                    if not row[2]: null_fields.append('comp_brand')
                    if not row[3]: null_fields.append('comp_sku_name')
                    if not row[4]: null_fields.append('calender_week')
                    if row[5] is None: null_fields.append('created_at')
                    if not row[6]: null_fields.append('batch_id')
                    if not row[7]: null_fields.append('category')

                    results.append({
                        'id': row[0],
                        'item': f"{row[2] or '-'} / {row[3] or '-'}",  # comp_brand / comp_sku_name
                        'crawl_datetime': str(row[5]) if row[5] else None,
                        'null_fields': null_fields
                    })

            elif retailer == 'Forecast':
                # Forecast NULL 상세
                query = """
                    SELECT id, product_name, event, metric_type, event_offset, event_value, comment, week, crawled_at
                    FROM openai_forecast_results
                    WHERE DATE(crawled_at) = %s
                      AND (product_name IS NULL OR product_name = ''
                          OR event IS NULL OR event = ''
                          OR metric_type IS NULL OR metric_type = ''
                          OR event_offset IS NULL
                          OR event_value IS NULL
                          OR comment IS NULL OR comment = ''
                          OR week IS NULL OR week = ''
                          OR crawled_at IS NULL)
                    ORDER BY crawled_at DESC
                    LIMIT 200
                """
                cursor.execute(query, (target_date,))
                rows = cursor.fetchall()

                for row in rows:
                    null_fields = []
                    if not row[1]: null_fields.append('product_name')
                    if not row[2]: null_fields.append('event')
                    if not row[3]: null_fields.append('metric_type')
                    if row[4] is None: null_fields.append('event_offset')
                    if row[5] is None: null_fields.append('event_value')
                    if not row[6]: null_fields.append('comment')
                    if not row[7]: null_fields.append('week')
                    if row[8] is None: null_fields.append('crawled_at')

                    results.append({
                        'id': row[0],
                        'item': f"{row[1] or '-'} / {row[2] or '-'}",  # product_name / event
                        'crawl_datetime': str(row[8]) if row[8] else None,
                        'null_fields': null_fields
                    })

        else:
            results = []

        cursor.close()
        conn.close()

        return JsonResponse({
            'date': str(target_date),
            'table': table,
            'retailer': retailer,
            'total': len(results),
            'results': results
        })

    except Exception as e:
        return JsonResponse({'error': str(e)})


def format_detail(request):
    """형식 오류 상세 조회 API"""
    date_str = request.GET.get('date')
    table = request.GET.get('table', 'tv_retail')
    retailer = request.GET.get('retailer')

    if date_str:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    else:
        target_date = (datetime.now() - timedelta(days=1)).date()

    try:
        conn = get_dx_connection()
        cursor = conn.cursor()

        results = []
        next_date = target_date + timedelta(days=1)

        # TV Retail 형식 오류 상세 조회 - validate_tv_field 함수 사용 (layer_stats와 동일)
        if table == 'tv_retail':
            # layer_stats와 동일한 쿼리로 모든 필드 조회
            query = """
                SELECT
                    id, crawl_datetime, account_name, item, page_type, product_url,
                    main_rank, bsr_rank, final_sku_price, original_sku_price,
                    count_of_reviews, star_rating, count_of_star_ratings,
                    detailed_review_content,
                    number_of_units_purchased_past_month, available_quantity_for_purchase,
                    sku_popularity, retailer_membership_discounts,
                    rank_1, rank_2, summarized_review_content,
                    savings, offer, retailer_sku_name_similar, recommendation_intent,
                    number_of_ppl_purchased_yesterday, number_of_ppl_added_to_carts, discount_type
                FROM tv_retail_com
                WHERE crawl_datetime::timestamp >= %s AND crawl_datetime::timestamp < %s
            """
            params = [str(target_date), str(next_date)]

            if retailer:
                query += " AND account_name = %s"
                params.append(retailer)

            query += " ORDER BY account_name, crawl_datetime LIMIT 500"
            cursor.execute(query, params)
            rows = cursor.fetchall()

            # 전체 필드 목록 (layer_stats와 동일)
            all_fields = [
                'item', 'page_type', 'product_url', 'main_rank', 'bsr_rank',
                'final_sku_price', 'original_sku_price',
                'count_of_reviews', 'star_rating', 'count_of_star_ratings',
                'detailed_review_content',
                'number_of_units_purchased_past_month', 'available_quantity_for_purchase',
                'sku_popularity', 'retailer_membership_discounts',
                'rank_1', 'rank_2', 'summarized_review_content',
                'savings', 'offer', 'retailer_sku_name_similar', 'recommendation_intent',
                'number_of_ppl_purchased_yesterday', 'number_of_ppl_added_to_carts', 'discount_type'
            ]

            for row in rows:
                errors = []
                record_id = row[0]
                crawl_dt = row[1]
                account_name = row[2]
                item = row[3]
                product_url = row[5]

                # row[3]부터 시작 (row[0]=id, row[1]=crawl_datetime, row[2]=account_name)
                values = list(row[3:])

                for field, value in zip(all_fields, values):
                    error = validate_tv_field(field, value, account_name)
                    if error:
                        errors.append({
                            'field': field,
                            'value': str(value)[:50] if value else '',
                            'rule': error.split(':')[0] if ':' in error else error,
                            'reason': error.split(':')[1].strip() if ':' in error else error
                        })

                # 크로스 필드 검증 추가
                row_data = dict(zip(all_fields, values))
                cross_errors = validate_cross_field(row_data, account_name)
                for ce in cross_errors:
                    errors.append({
                        'field': ce['field'],
                        'value': ce['value'],
                        'rule': ce['field'],
                        'reason': ce['error']
                    })

                if errors:
                    results.append({
                        'id': record_id,
                        'item': item,
                        'crawl_datetime': str(crawl_dt) if crawl_dt else None,
                        'product_url': product_url,
                        'errors': errors
                    })

        # HHP Retail 형식 오류 상세 조회 - validate_hhp_field 함수 사용 (layer_stats와 동일)
        elif table == 'hhp_retail':
            # layer_stats와 동일한 쿼리로 모든 필드 조회
            query = """
                SELECT
                    id, crawl_strdatetime, account_name, item, page_type, product_url,
                    main_rank, bsr_rank, trend_rank, final_sku_price, original_sku_price,
                    count_of_reviews, star_rating, count_of_star_ratings,
                    detailed_review_content, trade_in, sku_status,
                    number_of_units_purchased_past_month, available_quantity_for_purchase,
                    sku_popularity, retailer_membership_discounts,
                    rank_1, rank_2, summarized_review_content,
                    savings, offer, retailer_sku_name_similar, recommendation_intent,
                    number_of_ppl_purchased_yesterday, number_of_ppl_added_to_carts, discount_type
                FROM hhp_retail_com
                WHERE crawl_strdatetime::timestamp >= %s AND crawl_strdatetime::timestamp < %s
            """
            params = [str(target_date), str(next_date)]

            if retailer:
                query += " AND account_name = %s"
                params.append(retailer)

            query += " ORDER BY account_name, crawl_strdatetime LIMIT 500"
            cursor.execute(query, params)
            rows = cursor.fetchall()

            # HHP 전용 필드 목록 (layer_stats와 동일 - trend_rank, trade_in, sku_status 포함)
            hhp_fields = [
                'item', 'page_type', 'product_url', 'main_rank', 'bsr_rank', 'trend_rank',
                'final_sku_price', 'original_sku_price',
                'count_of_reviews', 'star_rating', 'count_of_star_ratings',
                'detailed_review_content', 'trade_in', 'sku_status',
                'number_of_units_purchased_past_month', 'available_quantity_for_purchase',
                'sku_popularity', 'retailer_membership_discounts',
                'rank_1', 'rank_2', 'summarized_review_content',
                'savings', 'offer', 'retailer_sku_name_similar', 'recommendation_intent',
                'number_of_ppl_purchased_yesterday', 'number_of_ppl_added_to_carts', 'discount_type'
            ]

            for row in rows:
                errors = []
                record_id = row[0]
                crawl_dt = row[1]
                account_name = row[2]
                item = row[3]
                product_url = row[5]

                # row[3]부터 시작 (row[0]=id, row[1]=crawl_strdatetime, row[2]=account_name)
                values = list(row[3:])

                for field, value in zip(hhp_fields, values):
                    error = validate_hhp_field(field, value, account_name)
                    if error:
                        errors.append({
                            'field': field,
                            'value': str(value)[:50] if value else '',
                            'rule': error.split(':')[0] if ':' in error else error,
                            'reason': error.split(':')[1].strip() if ':' in error else error
                        })

                # 크로스 필드 검증 추가
                row_data = dict(zip(hhp_fields, values))
                cross_errors = validate_cross_field(row_data, account_name)
                for ce in cross_errors:
                    errors.append({
                        'field': ce['field'],
                        'value': ce['value'],
                        'rule': ce['field'],
                        'reason': ce['error']
                    })

                if errors:
                    results.append({
                        'id': record_id,
                        'item': item,
                        'crawl_datetime': str(crawl_dt) if crawl_dt else None,
                        'product_url': product_url,
                        'errors': errors
                    })

        # YouTube 테이블 형식 오류 상세 조회
        elif table == 'youtube' and retailer == 'Logs':
            # 먼저 active 키워드 목록 조회
            cursor.execute("SELECT keyword FROM youtube_keywords WHERE status = 'active'")
            active_keywords = set(row[0] for row in cursor.fetchall())

            # 형식 오류가 있는 로그 조회
            cursor.execute("""
                SELECT l.id, l.keyword, l.status, l.videos_collected, l.comments_collected, l.started_at
                FROM youtube_collection_logs l
                WHERE DATE(l.started_at) = %s
                  AND (
                      (l.keyword IS NOT NULL AND l.keyword NOT IN (SELECT keyword FROM youtube_keywords WHERE status = 'active'))
                      OR (l.status IS NOT NULL AND l.status NOT IN ('failed', 'completed'))
                      OR (l.videos_collected IS NOT NULL AND l.videos_collected < 0)
                      OR (l.comments_collected IS NOT NULL AND l.comments_collected < 0)
                  )
                ORDER BY l.started_at DESC
                LIMIT 50
            """, (target_date,))
            rows = cursor.fetchall()
            for row in rows:
                errors = []
                # keyword가 active 키워드 목록에 없으면 오류
                if row[1] and row[1] not in active_keywords:
                    errors.append({
                        'field': 'keyword',
                        'value': str(row[1])[:50],
                        'rule': 'active 키워드만 허용',
                        'reason': '비활성 키워드 사용'
                    })
                if row[2] and row[2] not in ('failed', 'completed'):
                    errors.append({
                        'field': 'status',
                        'value': str(row[2]),
                        'rule': 'failed 또는 completed',
                        'reason': f'허용되지 않은 값: {row[2]}'
                    })
                if row[3] is not None and row[3] < 0:
                    errors.append({
                        'field': 'videos_collected',
                        'value': str(row[3]),
                        'rule': '0 이상',
                        'reason': '음수값'
                    })
                if row[4] is not None and row[4] < 0:
                    errors.append({
                        'field': 'comments_collected',
                        'value': str(row[4]),
                        'rule': '0 이상',
                        'reason': '음수값'
                    })
                # 오류가 있을 때만 결과에 추가
                if errors:
                    results.append({
                        'id': row[0],
                        'keyword': row[1],
                        'status': row[2],
                        'videos_collected': row[3],
                        'comments_collected': row[4],
                        'started_at': str(row[5]) if row[5] else None,
                        'errors': errors
                    })

        elif table == 'youtube' and retailer == 'Videos':
            cursor.execute("""
                SELECT v.id, v.video_id, v.keyword, v.channel_custom_url, v.category,
                       v.engagement_rate, v.product_sentiment_score, v.published_at, v.created_at
                FROM youtube_videos v
                WHERE DATE(v.created_at) = %s
                  AND (
                      (v.keyword IS NOT NULL AND v.keyword NOT IN (SELECT keyword FROM youtube_keywords WHERE status = 'active'))
                      OR (v.published_at IS NOT NULL AND v.created_at IS NOT NULL AND v.published_at > v.created_at)
                      OR (v.channel_custom_url IS NOT NULL AND v.channel_custom_url != '' AND LEFT(v.channel_custom_url, 1) != '@')
                      OR (v.category IS NOT NULL AND v.category NOT IN ('TV', 'HHP'))
                      OR (v.engagement_rate IS NOT NULL AND v.engagement_rate < 2.0)
                      OR (v.product_sentiment_score IS NOT NULL AND (v.product_sentiment_score < -5.0 OR v.product_sentiment_score > 5.0))
                  )
                ORDER BY v.created_at DESC
                LIMIT 50
            """, (target_date,))
            rows = cursor.fetchall()
            for row in rows:
                errors = []
                if row[3] and not row[3].startswith('@'):
                    errors.append({
                        'field': 'channel_custom_url',
                        'value': str(row[3])[:50],
                        'rule': '@로 시작',
                        'reason': '@ 누락'
                    })
                if row[4] and row[4] not in ('TV', 'HHP'):
                    errors.append({
                        'field': 'category',
                        'value': str(row[4]),
                        'rule': 'TV 또는 HHP',
                        'reason': f'허용되지 않은 값: {row[4]}'
                    })
                if row[5] is not None and row[5] < 2.0:
                    errors.append({
                        'field': 'engagement_rate',
                        'value': str(row[5]),
                        'rule': '2.0 이상',
                        'reason': '기준치 미달'
                    })
                if row[6] is not None and (row[6] < -5.0 or row[6] > 5.0):
                    errors.append({
                        'field': 'product_sentiment_score',
                        'value': str(row[6]),
                        'rule': '-5.0 ~ 5.0 범위',
                        'reason': '범위 초과'
                    })
                if row[7] and row[8] and row[7] > row[8]:
                    errors.append({
                        'field': 'published_at',
                        'value': str(row[7])[:19],
                        'rule': 'published_at <= created_at',
                        'reason': '수집일보다 미래의 발행일'
                    })
                results.append({
                    'id': row[0],
                    'video_id': row[1],
                    'keyword': row[2],
                    'channel_custom_url': row[3],
                    'category': row[4],
                    'engagement_rate': float(row[5]) if row[5] else None,
                    'product_sentiment_score': float(row[6]) if row[6] else None,
                    'errors': errors
                })

        elif table == 'youtube' and retailer == 'Comments':
            # 각 레코드별 오류 검증 플래그를 SQL에서 직접 계산
            cursor.execute("""
                SELECT c.comment_id, c.video_id, c.comment_type, c.parent_comment_id, c.like_count, c.reply_count,
                       c.published_at, c.created_at,
                       CASE WHEN c.video_id IS NOT NULL AND c.video_id NOT IN (SELECT video_id FROM youtube_videos) THEN 1 ELSE 0 END as video_id_invalid,
                       CASE WHEN c.comment_type IS NOT NULL AND c.comment_type NOT IN ('top_level', 'reply') THEN 1 ELSE 0 END as comment_type_invalid,
                       CASE WHEN c.parent_comment_id IS NOT NULL AND c.parent_comment_id != '' AND c.comment_type = 'top_level' THEN 1 ELSE 0 END as parent_invalid,
                       CASE WHEN c.like_count IS NOT NULL AND c.like_count < 0 THEN 1 ELSE 0 END as like_count_invalid,
                       CASE WHEN c.reply_count IS NOT NULL AND c.reply_count < 0 THEN 1 ELSE 0 END as reply_count_invalid,
                       CASE WHEN c.published_at IS NOT NULL AND c.created_at IS NOT NULL AND c.published_at > c.created_at THEN 1 ELSE 0 END as published_at_invalid
                FROM youtube_comments c
                WHERE DATE(c.created_at) = %s
                  AND (
                      (c.video_id IS NOT NULL AND c.video_id NOT IN (SELECT video_id FROM youtube_videos))
                      OR (c.comment_type IS NOT NULL AND c.comment_type NOT IN ('top_level', 'reply'))
                      OR (c.parent_comment_id IS NOT NULL AND c.parent_comment_id != '' AND c.comment_type = 'top_level')
                      OR (c.like_count IS NOT NULL AND c.like_count < 0)
                      OR (c.reply_count IS NOT NULL AND c.reply_count < 0)
                      OR (c.published_at IS NOT NULL AND c.created_at IS NOT NULL AND c.published_at > c.created_at)
                  )
                ORDER BY c.comment_id DESC
            """, (target_date,))
            rows = cursor.fetchall()

            for row in rows:
                errors = []
                # row[8] ~ row[13]: 각 검증 플래그
                if row[8] == 1:  # video_id_invalid
                    errors.append({
                        'field': 'video_id',
                        'value': str(row[1])[:50],
                        'rule': 'youtube_videos 참조',
                        'reason': '존재하지 않는 video_id'
                    })
                if row[9] == 1:  # comment_type_invalid
                    errors.append({
                        'field': 'comment_type',
                        'value': str(row[2]),
                        'rule': 'top_level 또는 reply',
                        'reason': f'허용되지 않은 값: {row[2]}'
                    })
                if row[10] == 1:  # parent_invalid
                    errors.append({
                        'field': 'parent_comment_id',
                        'value': str(row[3])[:50],
                        'rule': 'top_level은 빈값',
                        'reason': 'top_level인데 parent 존재'
                    })
                if row[11] == 1:  # like_count_invalid
                    errors.append({
                        'field': 'like_count',
                        'value': str(row[4]),
                        'rule': '0 이상',
                        'reason': '음수값'
                    })
                if row[12] == 1:  # reply_count_invalid
                    errors.append({
                        'field': 'reply_count',
                        'value': str(row[5]),
                        'rule': '0 이상',
                        'reason': '음수값'
                    })
                if row[13] == 1:  # published_at_invalid
                    errors.append({
                        'field': 'published_at',
                        'value': str(row[6])[:19],
                        'rule': 'published_at <= created_at',
                        'reason': '수집일보다 미래의 발행일'
                    })

                if errors:
                    results.append({
                        'id': row[0],
                        'video_id': row[1],
                        'comment_type': row[2],
                        'parent_comment_id': row[3],
                        'like_count': row[4],
                        'reply_count': row[5],
                        'errors': errors
                    })

        elif table == 'market' and retailer == 'Trend':
            # market_trend 형식 오류 조회
            cursor.execute("SELECT keyword FROM market_mst WHERE analysis_type = 'trend'")
            valid_keywords = set(row[0] for row in cursor.fetchall())

            cursor.execute("""
                SELECT id, keyword, total_article_number, calendar_week, crawl_at_local_time,
                       CASE WHEN keyword IS NOT NULL AND keyword != '' THEN 1 ELSE 0 END as has_keyword,
                       CASE WHEN total_article_number IS NOT NULL THEN 1 ELSE 0 END as has_total,
                       CASE WHEN calendar_week IS NOT NULL AND calendar_week != '' THEN 1 ELSE 0 END as has_week
                FROM market_trend
                WHERE DATE(crawl_at_local_time) = %s
                  AND (
                      (keyword IS NOT NULL AND keyword != '')
                      OR (total_article_number IS NOT NULL AND total_article_number < 0)
                      OR (calendar_week IS NOT NULL AND calendar_week != '' AND calendar_week !~ '^W([1-9]|[1-4][0-9]|5[0-2])$')
                  )
                ORDER BY crawl_at_local_time DESC
            """, (target_date,))
            rows = cursor.fetchall()

            for row in rows:
                errors = []
                keyword = row[1]
                total_article = row[2]
                cal_week = row[3]

                # keyword가 market_mst에 없으면 오류
                if keyword and keyword not in valid_keywords:
                    errors.append({
                        'field': 'keyword',
                        'value': str(keyword)[:50],
                        'rule': 'market_mst 등록 키워드',
                        'reason': '미등록 키워드'
                    })
                # total_article_number 음수
                if total_article is not None and total_article < 0:
                    errors.append({
                        'field': 'total_article_number',
                        'value': str(total_article),
                        'rule': '0 이상',
                        'reason': '음수값'
                    })
                # calendar_week 형식 오류 (W1~W52)
                import re as re_module
                if cal_week and not re_module.match(r'^W([1-9]|[1-4][0-9]|5[0-2])$', cal_week):
                    errors.append({
                        'field': 'calendar_week',
                        'value': str(cal_week),
                        'rule': 'W1 ~ W52',
                        'reason': '형식 오류'
                    })

                if errors:
                    results.append({
                        'id': row[0],
                        'keyword': keyword,
                        'total_article_number': total_article,
                        'calendar_week': cal_week,
                        'errors': errors
                    })

        elif table == 'market' and retailer == 'Comp Product':
            # market_comp_product 형식 오류 조회
            cursor.execute("SELECT keyword FROM market_mst WHERE analysis_type = 'competitor' AND content_type = 'samsung'")
            valid_samsung = set(row[0] for row in cursor.fetchall())
            cursor.execute("SELECT keyword FROM market_mst WHERE analysis_type = 'competitor' AND content_type = 'comp'")
            valid_comp = set(row[0] for row in cursor.fetchall())

            cursor.execute("""
                SELECT id, samsung_series_name, comp_brand, calender_week, category, created_at
                FROM market_comp_product
                WHERE DATE(created_at) = %s
                  AND (
                      (samsung_series_name IS NOT NULL AND samsung_series_name != '')
                      OR (comp_brand IS NOT NULL AND comp_brand != '')
                      OR (calender_week IS NOT NULL AND calender_week != '' AND LOWER(calender_week) !~ '^w([1-9]|[1-4][0-9]|5[0-2])$')
                      OR (category IS NOT NULL AND category != '' AND category NOT IN ('TV', 'HHP'))
                  )
                ORDER BY created_at DESC
            """, (target_date,))
            rows = cursor.fetchall()

            for row in rows:
                errors = []
                samsung_name = row[1]
                comp_brand = row[2]
                cal_week = row[3]
                category = row[4]

                if samsung_name and samsung_name not in valid_samsung:
                    errors.append({
                        'field': 'samsung_series_name',
                        'value': str(samsung_name)[:50],
                        'rule': 'market_mst 등록',
                        'reason': '미등록 시리즈'
                    })
                if comp_brand and comp_brand not in valid_comp:
                    errors.append({
                        'field': 'comp_brand',
                        'value': str(comp_brand)[:50],
                        'rule': 'market_mst 등록',
                        'reason': '미등록 브랜드'
                    })
                import re as re_module
                if cal_week and not re_module.match(r'^[wW]([1-9]|[1-4][0-9]|5[0-2])$', cal_week):
                    errors.append({
                        'field': 'calender_week',
                        'value': str(cal_week),
                        'rule': 'w1 ~ w52',
                        'reason': '형식 오류'
                    })
                if category and category not in ('TV', 'HHP'):
                    errors.append({
                        'field': 'category',
                        'value': str(category),
                        'rule': 'TV 또는 HHP',
                        'reason': '허용되지 않은 값'
                    })

                if errors:
                    results.append({
                        'id': row[0],
                        'samsung_series_name': samsung_name,
                        'comp_brand': comp_brand,
                        'calender_week': cal_week,
                        'category': category,
                        'errors': errors
                    })

        elif table == 'market' and retailer == 'Comp Event':
            # market_comp_event 형식 오류 조회 - 최신 배치 기준
            cursor.execute("""
                SELECT comp_brand, comp_series_name FROM market_comp_product
                WHERE batch_id = (SELECT MAX(batch_id) FROM market_comp_product WHERE DATE(created_at) <= %s)
            """, (target_date,))
            latest_batch = cursor.fetchall()
            valid_comp_brands = set(row[0] for row in latest_batch if row[0])
            valid_comp_skus = set(row[1] for row in latest_batch if row[1])

            cursor.execute("""
                SELECT id, comp_brand, comp_sku_name, calender_week, category, created_at
                FROM market_comp_event
                WHERE DATE(created_at) = %s
                  AND (
                      (comp_brand IS NOT NULL AND comp_brand != '')
                      OR (comp_sku_name IS NOT NULL AND comp_sku_name != '')
                      OR (calender_week IS NOT NULL AND calender_week != '' AND LOWER(calender_week) !~ '^w([1-9]|[1-4][0-9]|5[0-2])$')
                      OR (category IS NOT NULL AND category != '' AND category NOT IN ('TV', 'HHP'))
                  )
                ORDER BY created_at DESC
            """, (target_date,))
            rows = cursor.fetchall()

            for row in rows:
                errors = []
                comp_brand = row[1]
                comp_sku = row[2]
                cal_week = row[3]
                category = row[4]

                if comp_brand and comp_brand not in valid_comp_brands:
                    errors.append({
                        'field': 'comp_brand',
                        'value': str(comp_brand)[:50],
                        'rule': 'market_comp_product 참조',
                        'reason': '미등록 브랜드'
                    })
                if comp_sku and comp_sku not in valid_comp_skus:
                    errors.append({
                        'field': 'comp_sku_name',
                        'value': str(comp_sku)[:50],
                        'rule': 'market_comp_product 참조',
                        'reason': '미등록 SKU'
                    })
                import re as re_module
                if cal_week and not re_module.match(r'^[wW]([1-9]|[1-4][0-9]|5[0-2])$', cal_week):
                    errors.append({
                        'field': 'calender_week',
                        'value': str(cal_week),
                        'rule': 'w1 ~ w52',
                        'reason': '형식 오류'
                    })
                if category and category not in ('TV', 'HHP'):
                    errors.append({
                        'field': 'category',
                        'value': str(category),
                        'rule': 'TV 또는 HHP',
                        'reason': '허용되지 않은 값'
                    })

                if errors:
                    results.append({
                        'id': row[0],
                        'comp_brand': comp_brand,
                        'comp_sku_name': comp_sku,
                        'calender_week': cal_week,
                        'category': category,
                        'errors': errors
                    })

        elif table == 'market' and retailer == 'Forecast':
            # openai_forecast_results 형식 오류 조회
            cursor.execute("SELECT product_name FROM openai_keywords WHERE is_active = true")
            valid_products = set(row[0] for row in cursor.fetchall())
            cursor.execute("SELECT LOWER(REPLACE(event_name, ' ', '_')) FROM openai_event_mst WHERE is_active = true")
            valid_events = set(row[0] for row in cursor.fetchall())

            cursor.execute("""
                SELECT id, product_name, event, metric_type, event_offset, event_value, week, crawled_at
                FROM openai_forecast_results
                WHERE DATE(crawled_at) = %s
                  AND (
                      (product_name IS NOT NULL AND product_name != '')
                      OR (event IS NOT NULL AND event != '')
                      OR (metric_type IS NOT NULL AND metric_type != '' AND metric_type != 'Forecasted_NA_sales_change')
                      OR (event_offset IS NOT NULL AND (event_offset < 0 OR event_offset > 9))
                      OR (event_value IS NOT NULL AND event_value::text !~ '^-?[0-9]+\.?[0-9]*$')
                      OR (week IS NOT NULL AND week != '' AND week !~ '^w[0-9]{1,2}$')
                      OR (crawled_at IS NOT NULL AND crawled_at::text !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$')
                  )
                ORDER BY crawled_at DESC
                LIMIT 100
            """, (target_date,))
            rows = cursor.fetchall()

            import re as re_module
            for row in rows:
                errors = []
                product_name = row[1]
                event = row[2]
                metric_type = row[3]
                event_offset = row[4]
                event_value = row[5]
                week = row[6]
                crawled_at = row[7]

                if product_name and product_name not in valid_products:
                    errors.append({
                        'field': 'product_name',
                        'value': str(product_name)[:50],
                        'rule': 'openai_keywords 등록',
                        'reason': '미등록 제품'
                    })
                if event and event.lower().replace(' ', '_') not in valid_events:
                    errors.append({
                        'field': 'event',
                        'value': str(event)[:50],
                        'rule': 'openai_event_mst 등록',
                        'reason': '미등록 이벤트'
                    })
                if metric_type and metric_type != 'Forecasted_NA_sales_change':
                    errors.append({
                        'field': 'metric_type',
                        'value': str(metric_type)[:50],
                        'rule': 'Forecasted_NA_sales_change',
                        'reason': '허용되지 않은 값'
                    })
                if event_offset is not None and (event_offset < 0 or event_offset > 9):
                    errors.append({
                        'field': 'event_offset',
                        'value': str(event_offset),
                        'rule': '0 ~ 9',
                        'reason': '범위 초과'
                    })
                if event_value is not None and not re_module.match(r'^-?[0-9]+\.?[0-9]*$', str(event_value)):
                    errors.append({
                        'field': 'event_value',
                        'value': str(event_value)[:30],
                        'rule': '숫자 형식',
                        'reason': '형식 오류'
                    })
                if week and not re_module.match(r'^w[0-9]{1,2}$', week):
                    errors.append({
                        'field': 'week',
                        'value': str(week),
                        'rule': 'w + 숫자',
                        'reason': '형식 오류'
                    })
                if crawled_at and not re_module.match(r'^[0-9]{4}-[0-9]{2}-[0-9]{2}$', str(crawled_at)):
                    errors.append({
                        'field': 'crawled_at',
                        'value': str(crawled_at)[:20],
                        'rule': 'YYYY-MM-DD',
                        'reason': '형식 오류'
                    })

                if errors:
                    results.append({
                        'id': row[0],
                        'product_name': product_name,
                        'event': event,
                        'metric_type': metric_type,
                        'event_offset': event_offset,
                        'event_value': event_value,
                        'week': week,
                        'errors': errors
                    })

        cursor.close()
        conn.close()

        return JsonResponse({
            'date': str(target_date),
            'table': table,
            'retailer': retailer,
            'results': results
        })

    except Exception as e:
        return JsonResponse({'error': str(e)})


def anomaly_detail(request):
    """중복 검증 상세 조회 API - 리테일러별, 시간대별 중복 상세"""
    date_str = request.GET.get('date')
    table = request.GET.get('table', 'tv_retail')
    retailer = request.GET.get('retailer', '')

    if date_str:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    else:
        target_date = (datetime.now() - timedelta(days=1)).date()

    try:
        conn = get_dx_connection()
        cursor = conn.cursor()

        duplicates = []

        if table == 'tv_retail':
            # 중복 그룹 찾기: item + 시간대 (오전/오후 각각 1건만 있어야 정상)
            # page_type은 무시 - main과 bsr에서 같은 item이 수집되는 건 정상
            cursor.execute("""
                WITH duplicate_groups AS (
                    SELECT item, account_name,
                           CASE WHEN EXTRACT(HOUR FROM crawl_datetime::timestamp) < 12 THEN '오전' ELSE '오후' END as period,
                           COUNT(*) as dup_count
                    FROM tv_retail_com
                    WHERE DATE(crawl_datetime::timestamp) = %s
                      AND (%s = '' OR account_name = %s)
                    GROUP BY item, account_name, period
                    HAVING COUNT(*) > 1
                )
                SELECT d.item, d.account_name, d.period, d.dup_count,
                       t.id, t.product_url, t.crawl_datetime, t.page_type, t.main_rank, t.bsr_rank
                FROM duplicate_groups d
                JOIN tv_retail_com t ON t.item = d.item
                    AND t.account_name = d.account_name
                    AND DATE(t.crawl_datetime::timestamp) = %s
                    AND CASE WHEN EXTRACT(HOUR FROM t.crawl_datetime::timestamp) < 12 THEN '오전' ELSE '오후' END = d.period
                ORDER BY d.dup_count DESC, d.item, d.period, t.crawl_datetime
                LIMIT 200
            """, (target_date, retailer, retailer, target_date))

            rows = cursor.fetchall()

            # 중복 그룹별로 묶기
            dup_groups = {}
            for row in rows:
                key = (row[0], row[1], row[2])  # item, account_name, period
                if key not in dup_groups:
                    dup_groups[key] = {
                        'item': row[0],
                        'retailer': row[1],
                        'period': row[2],
                        'dup_count': row[3],
                        'reason': f'동일 item이 {row[2]}에 {row[3]}건 수집됨',
                        'records': []
                    }
                dup_groups[key]['records'].append({
                    'id': row[4],
                    'product_url': row[5],
                    'crawl_datetime': str(row[6]) if row[6] else None,
                    'page_type': row[7],
                    'main_rank': row[8],
                    'bsr_rank': row[9]
                })

            duplicates = list(dup_groups.values())

        elif table == 'hhp_retail':
            # 중복 그룹 찾기: item + 시간대 (오전/오후 각각 1건만 있어야 정상)
            cursor.execute("""
                WITH duplicate_groups AS (
                    SELECT item, account_name,
                           CASE WHEN EXTRACT(HOUR FROM crawl_strdatetime::timestamp) < 12 THEN '오전' ELSE '오후' END as period,
                           COUNT(*) as dup_count
                    FROM hhp_retail_com
                    WHERE DATE(crawl_strdatetime::timestamp) = %s
                      AND (%s = '' OR account_name = %s)
                    GROUP BY item, account_name, period
                    HAVING COUNT(*) > 1
                )
                SELECT d.item, d.account_name, d.period, d.dup_count,
                       h.id, h.product_url, h.crawl_strdatetime, h.page_type, h.main_rank, h.bsr_rank
                FROM duplicate_groups d
                JOIN hhp_retail_com h ON h.item = d.item
                    AND h.account_name = d.account_name
                    AND DATE(h.crawl_strdatetime::timestamp) = %s
                    AND CASE WHEN EXTRACT(HOUR FROM h.crawl_strdatetime::timestamp) < 12 THEN '오전' ELSE '오후' END = d.period
                ORDER BY d.dup_count DESC, d.item, d.period, h.crawl_strdatetime
                LIMIT 200
            """, (target_date, retailer, retailer, target_date))

            rows = cursor.fetchall()

            dup_groups = {}
            for row in rows:
                key = (row[0], row[1], row[2])  # item, account_name, period
                if key not in dup_groups:
                    dup_groups[key] = {
                        'item': row[0],
                        'retailer': row[1],
                        'period': row[2],
                        'dup_count': row[3],
                        'reason': f'동일 item이 {row[2]}에 {row[3]}건 수집됨',
                        'records': []
                    }
                dup_groups[key]['records'].append({
                    'id': row[4],
                    'product_url': row[5],
                    'crawl_datetime': str(row[6]) if row[6] else None,
                    'page_type': row[7],
                    'main_rank': row[8],
                    'bsr_rank': row[9]
                })

            duplicates = list(dup_groups.values())

        cursor.close()
        conn.close()

        return JsonResponse({
            'date': str(target_date),
            'table': table,
            'retailer': retailer,
            'results': {'duplicates': duplicates}
        })

    except Exception as e:
        return JsonResponse({'error': str(e)})


def null_columns(request):
    """모든 데이터가 NULL인 컬럼 탐지 API (리테일러별, 시간대별)"""
    date_str = request.GET.get('date')
    table = request.GET.get('table', 'tv_retail')

    if date_str:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    else:
        target_date = (datetime.now() - timedelta(days=1)).date()

    next_date = target_date + timedelta(days=1)

    try:
        conn = get_dx_connection()
        cursor = conn.cursor()

        if table == 'tv_retail':
            # TV Retail 컬럼 정의 (리테일러별)
            columns_by_retailer = {
                'Amazon': [
                    'id', 'item', 'account_name', 'page_type', 'product_url', 'screen_size',
                    'retailer_sku_name', 'count_of_reviews', 'star_rating', 'count_of_star_ratings',
                    'number_of_units_purchased_past_month', 'final_sku_price', 'original_sku_price',
                    'shipping_info', 'available_quantity_for_purchase', 'discount_type', 'sku_popularity',
                    'retailer_membership_discounts', 'rank_1', 'rank_2', 'summarized_review_content',
                    'detailed_review_content', 'main_rank', 'bsr_rank', 'calendar_week', 'crawl_datetime'
                ],
                'Bestbuy': [
                    'id', 'item', 'account_name', 'page_type', 'product_url', 'screen_size',
                    'retailer_sku_name', 'final_sku_price', 'original_sku_price', 'savings', 'offer',
                    'pick_up_availability', 'shipping_availability', 'delivery_availability',
                    'count_of_reviews', 'star_rating', 'count_of_star_ratings',
                    'estimated_annual_electricity_use', 'retailer_sku_name_similar', 'top_mentions',
                    'detailed_review_content', 'recommendation_intent', 'promotion_type',
                    'main_rank', 'bsr_rank', 'calendar_week', 'crawl_datetime'
                ],
                'Walmart': [
                    'id', 'item', 'account_name', 'page_type', 'product_url', 'screen_size',
                    'retailer_sku_name', 'final_sku_price', 'original_sku_price', 'offer',
                    'pick_up_availability', 'shipping_availability', 'delivery_availability',
                    'sku_status', 'retailer_membership_discounts', 'available_quantity_for_purchase',
                    'inventory_status', 'number_of_ppl_purchased_yesterday', 'number_of_ppl_added_to_carts',
                    'sku_popularity', 'savings', 'discount_type', 'shipping_info', 'count_of_reviews',
                    'star_rating', 'count_of_star_ratings', 'detailed_review_content',
                    'main_rank', 'bsr_rank', 'calendar_week', 'crawl_datetime'
                ]
            }

            results = {}
            for retailer, columns in columns_by_retailer.items():
                results[retailer] = {'오전': [], '오후': []}

                for period, hour_condition in [('오전', '< 12'), ('오후', '>= 12')]:
                    # 한 번의 쿼리로 모든 컬럼 COUNT
                    count_parts = [f"COUNT({col}) as {col}_cnt" for col in columns]
                    query = f"""
                        SELECT {', '.join(count_parts)}
                        FROM tv_retail_com
                        WHERE account_name = %s
                        AND crawl_datetime::timestamp >= %s
                        AND crawl_datetime::timestamp < %s
                        AND EXTRACT(HOUR FROM crawl_datetime::timestamp) {hour_condition}
                    """

                    cursor.execute(query, (retailer, str(target_date), str(next_date)))
                    row = cursor.fetchone()

                    if row:
                        # COUNT = 0 인 컬럼 = 모든 데이터가 NULL
                        null_cols = [col for col, cnt in zip(columns, row) if cnt == 0]
                        results[retailer][period] = null_cols

        elif table == 'hhp_retail':
            # HHP Retail 컬럼 정의 (리테일러별)
            columns_by_retailer = {
                'Amazon': [
                    'id', 'country', 'product', 'item', 'account_name', 'page_type', 'product_url', 'main_rank', 'bsr_rank',
                    'retailer_sku_name', 'number_of_units_purchased_past_month', 'final_sku_price', 'original_sku_price',
                    'shipping_info', 'available_quantity_for_purchase', 'discount_type',
                    'count_of_reviews', 'star_rating', 'count_of_star_ratings',
                    'sku_popularity', 'bundle', 'trade_in', 'retailer_membership_discounts', 'rank_1', 'rank_2',
                    'hhp_carrier', 'hhp_storage', 'hhp_color', 'summarized_review_content', 'detailed_review_content',
                    'calendar_week', 'crawl_strdatetime'
                ],
                'Bestbuy': [
                    'id', 'country', 'product', 'item', 'account_name', 'page_type', 'count_of_reviews',
                    'retailer_sku_name', 'product_url', 'star_rating', 'count_of_star_ratings',
                    'final_sku_price', 'original_sku_price', 'savings', 'offer',
                    'pick_up_availability', 'shipping_availability', 'delivery_availability', 'sku_status',
                    'trade_in', 'hhp_carrier', 'hhp_storage', 'hhp_color', 'detailed_review_content', 'top_mentions',
                    'recommendation_intent', 'main_rank', 'bsr_rank', 'trend_rank',
                    'promotion_type', 'retailer_sku_name_similar', 'calendar_week', 'crawl_strdatetime'
                ],
                'Walmart': [
                    'id', 'item', 'account_name', 'page_type', 'product_url',
                    'retailer_sku_name', 'final_sku_price', 'original_sku_price', 'offer',
                    'pick_up_availability', 'shipping_availability', 'delivery_availability', 'sku_status',
                    'retailer_membership_discounts', 'available_quantity_for_purchase', 'inventory_status',
                    'number_of_ppl_purchased_yesterday', 'number_of_ppl_added_to_carts',
                    'sku_popularity', 'savings', 'discount_type', 'shipping_info',
                    'hhp_carrier', 'hhp_storage', 'hhp_color', 'retailer_sku_name_similar', 'detailed_review_content',
                    'count_of_reviews', 'star_rating', 'count_of_star_ratings', 'main_rank', 'bsr_rank',
                    'calendar_week', 'crawl_strdatetime'
                ]
            }

            results = {}
            for retailer, columns in columns_by_retailer.items():
                results[retailer] = {'오전': [], '오후': []}

                for period, hour_condition in [('오전', '< 12'), ('오후', '>= 12')]:
                    count_parts = [f"COUNT({col}) as {col}_cnt" for col in columns]
                    query = f"""
                        SELECT {', '.join(count_parts)}
                        FROM hhp_retail_com
                        WHERE account_name = %s
                        AND crawl_strdatetime::timestamp >= %s
                        AND crawl_strdatetime::timestamp < %s
                        AND EXTRACT(HOUR FROM crawl_strdatetime::timestamp) {hour_condition}
                    """

                    cursor.execute(query, (retailer, str(target_date), str(next_date)))
                    row = cursor.fetchone()

                    if row:
                        null_cols = [col for col, cnt in zip(columns, row) if cnt == 0]
                        results[retailer][period] = null_cols

        else:
            results = {}

        cursor.close()
        conn.close()

        return JsonResponse({
            'date': str(target_date),
            'table': table,
            'results': results
        })

    except Exception as e:
        return JsonResponse({'error': str(e)})


# ============================================================
# DS (Samsung DS Retail) APIs
# ============================================================

# DS 모니터링 대상 테이블 정보
DS_MONITORING_TARGETS = [
    ('amazon_price_crawl_tbl_usa_v2', 'Amazon', '미국', 'usa', 'amazon'),
    ('bestbuy_price_crawl_tbl_usa_v2', 'Best Buy', '미국', 'usa', 'bestbuy'),
    ('amazon_price_crawl_tbl_jp_v2', 'Amazon', '일본', 'jp', 'amazon'),
    ('amazon_price_crawl_tbl_ind_v2', 'Amazon', '인도', 'in', 'amazon'),
    ('danawa_price_crawl_tbl_kr_v2', 'Danawa', '한국', 'kr', 'danawa'),
    ('amazon_price_crawl_tbl_uk_v2', 'Amazon', '영국', 'gb', 'amazon'),
    ('currys_price_crawl_tbl_gb_v2', 'Currys', '영국', 'gb', 'currys'),
    ('amazon_price_crawl_tbl_it_v2', 'Amazon', '이탈리아', 'it', 'amazon'),
    ('amazon_price_crawl_tbl_es_v2', 'Amazon', '스페인', 'es', 'amazon'),
    ('amazon_price_crawl_tbl_fr_v2', 'Amazon', '프랑스', 'fr', 'amazon'),
    ('fnac_price_crawl_tbl_fr', 'Fnac', '프랑스', 'fr', 'fnac'),
    ('amazon_price_crawl_tbl_nl', 'Amazon', '네덜란드', 'nl', 'amazon'),
    ('coolblue_price_crawl_tbl_nl_v2', 'Coolblue', '네덜란드', 'nl', 'coolblue'),
    ('amazon_price_crawl_tbl_de_v2', 'Amazon', '독일', 'de', 'amazon'),
    ('mediamarkt_price_crawl_tbl_de_v2', 'MediaMarkt', '독일', 'de', 'mediamarkt'),
    ('xkom_price_crawl_tbl_pl_v2', 'X-Kom', '폴란드', 'pl', 'x-kom'),
    ('centrecom_price_crawl_tbl_au', 'Centre Com', '호주', 'au', 'centrecom'),
]


def ds_layer_stats(request):
    """DS Layer 2 통계 API - NULL/형식/수집률 검증"""
    from apps.common.db import get_ds_connection

    date_str = request.GET.get('date')

    if date_str:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    else:
        target_date = (datetime.now() - timedelta(days=1)).date()

    date_str_compact = target_date.strftime('%Y%m%d')
    next_date_compact = (target_date + timedelta(days=1)).strftime('%Y%m%d')
    start_datetime = f"{date_str_compact}0000"
    end_datetime = f"{next_date_compact}0000"

    results = {
        'timestamp': datetime.now().isoformat(),
        'date': str(target_date),
        'layer': 2,
        'name': 'DS 형식/NULL 검수',
        'validation_types': [],
        'summary': {
            'total_issues': 0,
            'null_issues': 0,
            'format_issues': 0,
            'collection_issues': 0,
            'overall_status': 'OK'
        }
    }

    try:
        conn = get_ds_connection()
        cursor = conn.cursor()

        total_null_issues = 0
        total_format_issues = 0
        total_collection_issues = 0

        # ============================================================
        # 1. NULL 검증
        # ============================================================
        null_validation = {
            'type': 'null',
            'type_name': 'NULL 검증',
            'type_name_en': 'Null Validation',
            'description': '필수 필드(title, imageurl) NULL 검증',
            'icon': '🔍',
            'tables': []
        }

        # 지역별로 그룹화
        region_stats = {}

        for table_name, retailer, region, country, mall_name in DS_MONITORING_TARGETS:
            if region not in region_stats:
                region_stats[region] = {
                    'retailers': [],
                    'total_records': 0,
                    'null_issues': 0
                }

            try:
                # 전체 레코드 수
                cursor.execute(f"""
                    SELECT COUNT(*) FROM (
                        SELECT DISTINCT * FROM samsung_ds_retail_com.{table_name}
                        WHERE crawl_strdatetime >= %s AND crawl_strdatetime < %s
                    ) A
                """, (start_datetime, end_datetime))
                total_count = cursor.fetchone()[0] or 0

                # title NULL 개수
                cursor.execute(f"""
                    SELECT COUNT(*) FROM (
                        SELECT DISTINCT * FROM samsung_ds_retail_com.{table_name}
                        WHERE crawl_strdatetime >= %s AND crawl_strdatetime < %s
                    ) A WHERE (title IS NULL OR title = '')
                """, (start_datetime, end_datetime))
                null_title = cursor.fetchone()[0] or 0

                # imageurl NULL 또는 http로 시작하지 않음
                cursor.execute(f"""
                    SELECT COUNT(*) FROM (
                        SELECT DISTINCT * FROM samsung_ds_retail_com.{table_name}
                        WHERE crawl_strdatetime >= %s AND crawl_strdatetime < %s
                    ) A WHERE (imageurl IS NULL OR imageurl = '' OR imageurl NOT LIKE 'http%%')
                """, (start_datetime, end_datetime))
                null_imageurl = cursor.fetchone()[0] or 0

                null_total = null_title + null_imageurl

                region_stats[region]['retailers'].append({
                    'retailer': retailer,
                    'table': table_name,
                    'country': country,
                    'total': total_count,
                    'null_title': null_title,
                    'null_imageurl': null_imageurl,
                    'null_total': null_total,
                    'status': get_status(null_total)
                })
                region_stats[region]['total_records'] += total_count
                region_stats[region]['null_issues'] += null_total

            except Exception as e:
                region_stats[region]['retailers'].append({
                    'retailer': retailer,
                    'table': table_name,
                    'country': country,
                    'total': 0,
                    'null_title': 0,
                    'null_imageurl': 0,
                    'null_total': 0,
                    'status': 'ERROR',
                    'error': str(e)
                })

        # 지역별 NULL 검증 결과 추가
        for region, stats in region_stats.items():
            null_validation['tables'].append({
                'table': region,
                'table_name': f'{region}',
                'total_records': stats['total_records'],
                'total_issues': stats['null_issues'],
                'status': get_status(stats['null_issues']),
                'retailers': stats['retailers']
            })
            total_null_issues += stats['null_issues']

        null_validation['total_issues'] = total_null_issues
        null_validation['status'] = get_status(total_null_issues)
        results['validation_types'].append(null_validation)

        # ============================================================
        # 2. 형식 검증
        # ============================================================
        format_validation = {
            'type': 'format',
            'type_name': '형식 검증',
            'type_name_en': 'Format Validation',
            'description': 'retailprice, ships_from, sold_by 일관성 검증',
            'icon': '📋',
            'tables': []
        }

        format_by_region = {}

        for table_name, retailer, region, country, mall_name in DS_MONITORING_TARGETS:
            if region not in format_by_region:
                format_by_region[region] = {
                    'retailers': [],
                    'total_checked': 0,
                    'format_issues': 0
                }

            try:
                # 전체 레코드 수
                cursor.execute(f"""
                    SELECT COUNT(*) FROM (
                        SELECT DISTINCT * FROM samsung_ds_retail_com.{table_name}
                        WHERE crawl_strdatetime >= %s AND crawl_strdatetime < %s
                    ) A
                """, (start_datetime, end_datetime))
                total_count = cursor.fetchone()[0] or 0

                # retailprice 부분 NULL (title이 있는데 retailprice가 없고 다른 필드는 있는 경우)
                cursor.execute(f"""
                    SELECT COUNT(*) FROM (
                        SELECT DISTINCT * FROM samsung_ds_retail_com.{table_name}
                        WHERE crawl_strdatetime >= %s AND crawl_strdatetime < %s
                    ) A
                    WHERE (retailprice IS NULL OR retailprice = '')
                    AND (title IS NOT NULL AND title != '')
                    AND ((ships_from IS NOT NULL AND ships_from != '') OR (sold_by IS NOT NULL AND sold_by != ''))
                """, (start_datetime, end_datetime))
                format_retailprice = cursor.fetchone()[0] or 0

                # ships_from 부분 NULL
                cursor.execute(f"""
                    SELECT COUNT(*) FROM (
                        SELECT DISTINCT * FROM samsung_ds_retail_com.{table_name}
                        WHERE crawl_strdatetime >= %s AND crawl_strdatetime < %s
                    ) A
                    WHERE (ships_from IS NULL OR ships_from = '')
                    AND (title IS NOT NULL AND title != '')
                    AND ((retailprice IS NOT NULL AND retailprice != '') OR (sold_by IS NOT NULL AND sold_by != ''))
                """, (start_datetime, end_datetime))
                format_ships_from = cursor.fetchone()[0] or 0

                # sold_by 부분 NULL
                cursor.execute(f"""
                    SELECT COUNT(*) FROM (
                        SELECT DISTINCT * FROM samsung_ds_retail_com.{table_name}
                        WHERE crawl_strdatetime >= %s AND crawl_strdatetime < %s
                    ) A
                    WHERE (sold_by IS NULL OR sold_by = '')
                    AND (title IS NOT NULL AND title != '')
                    AND ((retailprice IS NOT NULL AND retailprice != '') OR (ships_from IS NOT NULL AND ships_from != ''))
                """, (start_datetime, end_datetime))
                format_sold_by = cursor.fetchone()[0] or 0

                format_total = format_retailprice + format_ships_from + format_sold_by

                format_by_region[region]['retailers'].append({
                    'retailer': retailer,
                    'table': table_name,
                    'country': country,
                    'total': total_count,
                    'format_retailprice': format_retailprice,
                    'format_ships_from': format_ships_from,
                    'format_sold_by': format_sold_by,
                    'format_total': format_total,
                    'status': get_status(format_total)
                })
                format_by_region[region]['total_checked'] += total_count
                format_by_region[region]['format_issues'] += format_total

            except Exception as e:
                format_by_region[region]['retailers'].append({
                    'retailer': retailer,
                    'table': table_name,
                    'country': country,
                    'total': 0,
                    'format_total': 0,
                    'status': 'ERROR',
                    'error': str(e)
                })

        # 지역별 형식 검증 결과 추가
        for region, stats in format_by_region.items():
            format_validation['tables'].append({
                'table': region,
                'table_name': f'{region}',
                'total_checked': stats['total_checked'],
                'total_issues': stats['format_issues'],
                'status': get_status(stats['format_issues']),
                'retailers': stats['retailers']
            })
            total_format_issues += stats['format_issues']

        format_validation['total_issues'] = total_format_issues
        format_validation['status'] = get_status(total_format_issues)
        results['validation_types'].append(format_validation)

        # ============================================================
        # 3. 수집률 검증
        # ============================================================
        collection_validation = {
            'type': 'collection',
            'type_name': '수집률 검증',
            'type_name_en': 'Collection Rate',
            'description': '예상 수집 건수 대비 실제 수집률',
            'icon': '📊',
            'tables': []
        }

        collection_by_region = {}

        for table_name, retailer, region, country, mall_name in DS_MONITORING_TARGETS:
            if region not in collection_by_region:
                collection_by_region[region] = {
                    'retailers': [],
                    'total_expected': 0,
                    'total_actual': 0
                }

            try:
                # 예상 수집 건수
                cursor.execute("""
                    SELECT COUNT(*) FROM samsung_ds_retail_com.samsung_price_tracking_list
                    WHERE country = %s AND mall_name = %s AND is_active = 1
                """, (country, mall_name))
                expected = cursor.fetchone()[0] or 0

                # 한국 다나와는 2배
                if country == 'kr' and mall_name == 'danawa':
                    expected = expected * 2

                # 실제 수집 건수
                cursor.execute(f"""
                    SELECT COUNT(*) FROM (
                        SELECT DISTINCT * FROM samsung_ds_retail_com.{table_name}
                        WHERE crawl_strdatetime >= %s AND crawl_strdatetime < %s
                    ) A
                """, (start_datetime, end_datetime))
                actual = cursor.fetchone()[0] or 0

                # 수집률 계산
                if expected > 0:
                    rate = round((actual / expected) * 100, 1)
                else:
                    rate = 0

                collection_by_region[region]['retailers'].append({
                    'retailer': retailer,
                    'table': table_name,
                    'country': country,
                    'expected': expected,
                    'actual': actual,
                    'rate': rate,
                    'status': 'OK' if rate >= 90 else ('WARNING' if rate >= 70 else 'CRITICAL')
                })
                collection_by_region[region]['total_expected'] += expected
                collection_by_region[region]['total_actual'] += actual

            except Exception as e:
                collection_by_region[region]['retailers'].append({
                    'retailer': retailer,
                    'table': table_name,
                    'country': country,
                    'expected': 0,
                    'actual': 0,
                    'rate': 0,
                    'status': 'ERROR',
                    'error': str(e)
                })

        # 지역별 수집률 결과 추가
        for region, stats in collection_by_region.items():
            if stats['total_expected'] > 0:
                region_rate = round((stats['total_actual'] / stats['total_expected']) * 100, 1)
            else:
                region_rate = 0

            # 90% 미만이면 이슈로 카운트
            issue_count = sum(1 for r in stats['retailers'] if r.get('rate', 0) < 90 and r.get('expected', 0) > 0)

            collection_validation['tables'].append({
                'table': region,
                'table_name': f'{region}',
                'total_expected': stats['total_expected'],
                'total_actual': stats['total_actual'],
                'rate': region_rate,
                'total_issues': issue_count,
                'status': 'OK' if region_rate >= 90 else ('WARNING' if region_rate >= 70 else 'CRITICAL'),
                'retailers': stats['retailers']
            })
            total_collection_issues += issue_count

        collection_validation['total_issues'] = total_collection_issues
        collection_validation['status'] = get_status(total_collection_issues)
        results['validation_types'].append(collection_validation)

        cursor.close()
        conn.close()

        # Summary 계산
        total_issues = total_null_issues + total_format_issues + total_collection_issues
        results['summary'] = {
            'total_issues': total_issues,
            'null_issues': total_null_issues,
            'format_issues': total_format_issues,
            'collection_issues': total_collection_issues,
            'overall_status': 'OK' if total_issues == 0 else ('WARNING' if total_issues <= 30 else 'CRITICAL')
        }

    except Exception as e:
        results['error'] = str(e)
        results['summary']['overall_status'] = 'ERROR'

    return JsonResponse(results)


def retailer_detail(request):
    """리테일러별 상세 오류 데이터 조회 API"""
    validation_type = request.GET.get('type', 'null')  # null, format, anomaly
    table_name = request.GET.get('table', '')  # TV Retail, HHP Retail
    retailer = request.GET.get('retailer', '')
    date_str = request.GET.get('date')

    if date_str:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    else:
        target_date = (datetime.now() - timedelta(days=1)).date()

    results = {
        'type': validation_type,
        'table': table_name,
        'retailer': retailer,
        'date': str(target_date),
        'records': [],
        'total': 0
    }

    try:
        conn = get_dx_connection()
        cursor = conn.cursor()

        # 테이블명 및 날짜 필드 결정
        if 'TV' in table_name:
            db_table = 'tv_retail_com'
            date_field = 'crawl_datetime'
            null_fields = ['item', 'screen_size', 'final_sku_price', 'retailer_sku_name',
                          'count_of_reviews', 'star_rating', 'count_of_star_ratings']
        elif 'HHP' in table_name:
            db_table = 'hhp_retail_com'
            date_field = 'crawl_strdatetime'
            null_fields = ['item', 'final_sku_price', 'retailer_sku_name',
                          'count_of_reviews', 'star_rating', 'count_of_star_ratings']
        else:
            return JsonResponse({'error': 'Invalid table name'}, status=400)

        if validation_type == 'null':
            # NULL 검증 상세 - 필수값 NULL인 레코드 조회
            null_conditions = ' OR '.join([f"({f} IS NULL OR {f} = '')" for f in null_fields])

            cursor.execute(f"""
                SELECT id, item, {date_field}, product_url,
                       {', '.join([f"CASE WHEN {f} IS NULL OR {f} = '' THEN 1 ELSE 0 END as null_{f}" for f in null_fields])}
                FROM {db_table}
                WHERE DATE({date_field}::timestamp) = %s
                  AND account_name = %s
                  AND ({null_conditions})
                ORDER BY id
                LIMIT 100
            """, (target_date, retailer))

            rows = cursor.fetchall()

            for row in rows:
                record_id = row[0]
                item = row[1]
                crawl_dt = row[2]
                product_url = row[3]

                # NULL인 필드들 찾기
                null_field_list = []
                for i, field in enumerate(null_fields):
                    if row[4 + i] == 1:
                        null_field_list.append(field)

                results['records'].append({
                    'id': record_id,
                    'item': item,
                    'product_url': product_url,
                    'null_fields': null_field_list,
                    'collected_at': str(crawl_dt) if crawl_dt else None
                })

            # 총 개수 조회
            cursor.execute(f"""
                SELECT COUNT(*)
                FROM {db_table}
                WHERE DATE({date_field}::timestamp) = %s
                  AND account_name = %s
                  AND ({null_conditions})
            """, (target_date, retailer))
            results['total'] = cursor.fetchone()[0]

        elif validation_type == 'format':
            # 형식 검증 상세 - TV와 HHP에 맞는 형식 오류 조회
            if 'TV' in table_name:
                format_errors = get_tv_format_errors(cursor, db_table, date_field, target_date, retailer)
            else:
                format_errors = get_hhp_format_errors(cursor, db_table, date_field, target_date, retailer)

            results['records'] = format_errors[:100]
            results['total'] = len(format_errors)

        elif validation_type == 'anomaly':
            # 이상치 검증 상세 - 중복 레코드 조회
            cursor.execute(f"""
                SELECT item, COUNT(*) as cnt
                FROM {db_table}
                WHERE DATE({date_field}::timestamp) = %s
                  AND account_name = %s
                GROUP BY item
                HAVING COUNT(*) > 1
                ORDER BY cnt DESC
                LIMIT 100
            """, (target_date, retailer))

            rows = cursor.fetchall()
            for row in rows:
                results['records'].append({
                    'id': '-',
                    'item': row[0],
                    'duplicate_type': f'중복 {row[1]}건',
                    'collected_at': str(target_date)
                })

            results['total'] = len(rows)

        cursor.close()
        conn.close()

    except Exception as e:
        results['error'] = str(e)

    return JsonResponse(results)


def get_tv_format_errors(cursor, table_name, date_field, target_date, retailer):
    """TV 형식 오류 데이터 조회"""
    errors = []

    # main_rank 검증 (1-400 범위)
    cursor.execute(f"""
        SELECT id, item, main_rank, {date_field}
        FROM {table_name}
        WHERE DATE({date_field}::timestamp) = %s
          AND account_name = %s
          AND main_rank IS NOT NULL
          AND main_rank != ''
          AND (
              NOT main_rank ~ '^[0-9]+$'
              OR CAST(main_rank AS INTEGER) < 1
              OR CAST(main_rank AS INTEGER) > 400
          )
        LIMIT 50
    """, (target_date, retailer))

    for row in cursor.fetchall():
        errors.append({
            'id': row[0],
            'item': row[1],
            'error_field': 'main_rank',
            'error_value': str(row[2]),
            'collected_at': str(row[3]) if row[3] else None
        })

    # star_rating 검증 (0.0-5.0)
    cursor.execute(f"""
        SELECT id, item, star_rating, {date_field}
        FROM {table_name}
        WHERE DATE({date_field}::timestamp) = %s
          AND account_name = %s
          AND star_rating IS NOT NULL
          AND star_rating != ''
          AND (
              NOT star_rating ~ '^[0-9]+(\\.[0-9]+)?$'
              OR CAST(star_rating AS NUMERIC) < 0
              OR CAST(star_rating AS NUMERIC) > 5
          )
        LIMIT 50
    """, (target_date, retailer))

    for row in cursor.fetchall():
        errors.append({
            'id': row[0],
            'item': row[1],
            'error_field': 'star_rating',
            'error_value': str(row[2]),
            'collected_at': str(row[3]) if row[3] else None
        })

    return errors


def get_hhp_format_errors(cursor, table_name, date_field, target_date, retailer):
    """HHP 형식 오류 데이터 조회"""
    errors = []

    # main_rank 검증 (1-300 범위)
    cursor.execute(f"""
        SELECT id, item, main_rank, {date_field}
        FROM {table_name}
        WHERE DATE({date_field}::timestamp) = %s
          AND account_name = %s
          AND main_rank IS NOT NULL
          AND main_rank != ''
          AND (
              NOT main_rank ~ '^[0-9]+$'
              OR CAST(main_rank AS INTEGER) < 1
              OR CAST(main_rank AS INTEGER) > 300
          )
        LIMIT 50
    """, (target_date, retailer))

    for row in cursor.fetchall():
        errors.append({
            'id': row[0],
            'item': row[1],
            'error_field': 'main_rank',
            'error_value': str(row[2]),
            'collected_at': str(row[3]) if row[3] else None
        })

    # star_rating 검증 (0.0-5.0)
    cursor.execute(f"""
        SELECT id, item, star_rating, {date_field}
        FROM {table_name}
        WHERE DATE({date_field}::timestamp) = %s
          AND account_name = %s
          AND star_rating IS NOT NULL
          AND star_rating != ''
          AND (
              NOT star_rating ~ '^[0-9]+(\\.[0-9]+)?$'
              OR CAST(star_rating AS NUMERIC) < 0
              OR CAST(star_rating AS NUMERIC) > 5
          )
        LIMIT 50
    """, (target_date, retailer))

    for row in cursor.fetchall():
        errors.append({
            'id': row[0],
            'item': row[1],
            'error_field': 'star_rating',
            'error_value': str(row[2]),
            'collected_at': str(row[3]) if row[3] else None
        })

    return errors
