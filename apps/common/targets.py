"""
모니터링 대상 설정 로드
CSV 파일에서 모니터링 타겟 목록을 읽어옴
"""

import csv
from pathlib import Path

# CSV 파일 경로 (config/csv 폴더)
TARGETS_CSV_PATH = Path(__file__).parent.parent.parent / 'config' / 'csv' / 'ds_monitoring_targets.csv'

# 캐시된 데이터
_targets_cache = None


def load_monitoring_targets():
    """
    CSV 파일에서 모니터링 대상 목록을 로드
    매번 CSV 파일에서 직접 읽음 (캐시 사용 안함)

    Returns:
        list of tuples: (table_name, retailer, region, korea_time, country, mall_name)
    """

    targets = []

    try:
        with open(TARGETS_CSV_PATH, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                targets.append((
                    row['table_name'],
                    row['retailer'],
                    row['region'],
                    row['korea_time'],
                    row['country'],
                    row['mall_name']
                ))
    except Exception as e:
        print(f"Error loading monitoring targets: {e}")

    return targets


def get_retailer_map():
    """
    country_mall_name -> retailer 매핑 딕셔너리 반환
    파일서버 조회용 (파일명에서 리테일러 찾기)

    예: 'de_amazon' -> 'Amazon_DE', 'de_mediamarkt' -> 'MediaMarkt'
    """
    targets = load_monitoring_targets()
    retailer_map = {}

    for table_name, retailer, region, korea_time, country, mall_name in targets:
        key = f"{country}_{mall_name}"
        retailer_map[key] = retailer

    return retailer_map


def reload_targets():
    """캐시 초기화 후 다시 로드 (CSV 수정 시 사용)"""
    global _targets_cache
    _targets_cache = None
    return load_monitoring_targets()


def get_report_targets():
    """
    Report용 모니터링 대상 목록 반환

    Returns:
        list of tuples: (table_name, retailer_display, country, mall_name)
        retailer_display는 소문자로 변환 (예: 'amazon_usa', 'bestbuy')
    """
    targets = load_monitoring_targets()
    report_targets = []

    for table_name, retailer, region, korea_time, country, mall_name in targets:
        # retailer_display 생성: retailer를 소문자로
        retailer_display = retailer.lower().replace('_', '_')
        report_targets.append((table_name, retailer_display, country, mall_name))

    return report_targets
