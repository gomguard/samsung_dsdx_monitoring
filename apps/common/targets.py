"""
모니터링 대상 설정 로드
DB에서 모니터링 타겟 목록을 읽어옴
"""

from datetime import timedelta
from apps.common.db import get_ds_connection

# 캐시된 데이터
_targets_cache = None


def format_time(time_value):
    """TIME 값을 HH:MM 형식 문자열로 변환"""
    if time_value is None:
        return '00:00'

    # timedelta인 경우 (MySQL TIME 타입)
    if isinstance(time_value, timedelta):
        total_seconds = int(time_value.total_seconds())
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        return f'{hours:02d}:{minutes:02d}'

    # datetime.time인 경우
    if hasattr(time_value, 'strftime'):
        return time_value.strftime('%H:%M')

    # 문자열인 경우
    time_str = str(time_value)
    # HH:MM:SS 형식에서 HH:MM만 추출
    parts = time_str.split(':')
    if len(parts) >= 2:
        return f'{int(parts[0]):02d}:{int(parts[1]):02d}'

    return time_str


def load_monitoring_targets():
    """
    DB에서 모니터링 대상 목록을 로드

    Returns:
        list of tuples: (table_name, retailer, region, korea_time, country, mall_name)
    """
    targets = []

    try:
        conn = get_ds_connection()
        cursor = conn.cursor()

        query = """
            SELECT table_name, retailer, region, korea_time, country, mall_name
            FROM ssd_crawl_db.ds_monitoring_targets
            WHERE is_active = TRUE
            ORDER BY id
        """
        cursor.execute(query)
        rows = cursor.fetchall()

        for row in rows:
            targets.append((
                row[0],                 # table_name
                row[1],                 # retailer
                row[2],                 # region
                format_time(row[3]),    # korea_time (HH:MM)
                row[4],                 # country
                row[5]                  # mall_name
            ))

        cursor.close()
        conn.close()

    except Exception as e:
        print(f"Error loading monitoring targets from DB: {e}")

    return targets


def load_monitoring_targets_with_local_time():
    """
    DB에서 모니터링 대상 목록을 로드 (local_time 포함)

    Returns:
        list of tuples: (table_name, retailer, region, korea_time, local_time, country, mall_name)
    """
    targets = []

    try:
        conn = get_ds_connection()
        cursor = conn.cursor()

        query = """
            SELECT table_name, retailer, region, korea_time, local_time, country, mall_name
            FROM ssd_crawl_db.ds_monitoring_targets
            WHERE is_active = TRUE
            ORDER BY id
        """
        cursor.execute(query)
        rows = cursor.fetchall()

        for row in rows:
            targets.append((
                row[0],                 # table_name
                row[1],                 # retailer
                row[2],                 # region
                format_time(row[3]),    # korea_time (HH:MM)
                format_time(row[4]),    # local_time (HH:MM)
                row[5],                 # country
                row[6]                  # mall_name
            ))

        cursor.close()
        conn.close()

    except Exception as e:
        print(f"Error loading monitoring targets from DB: {e}")

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
    """캐시 초기화 후 다시 로드"""
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
