"""
Macro Layer1 Services: view_table_name 기반 수집 건수 확인
- 예상건수 없음, 실행일별 수집 건수만 확인
- _make_service()로 check_type별 서비스 인스턴스 생성
"""

from datetime import timedelta
from apps.common.dx_schedules import get_schedules_by_type, get_schedule_kst_info, is_target_date as check_target_date
from apps.dx.dx_layer1.common.context import SECTION_TITLES
from . import macro_repositories as repo


def _get_next_target_date(schedule, target_date):
    """현재 날짜 이후 다음 분석대상일 계산"""
    d = target_date + timedelta(days=1)
    for _ in range(400):
        if check_target_date(schedule, d):
            return d
        d += timedelta(days=1)
    return None

_TABLE_MAP = {
    'macro_capital_stock': 'market_capital_stock',
    'macro_net_interest': 'market_net_interest',
    'macro_potential_gdp': 'market_potential_gdp',
    'macro_gdp_ppp_nominal': 'market_gdp_ppp_nominal',
    'macro_gdp_ppp_real': 'market_gdp_ppp_real',
    'macro_disposable_income_real': 'market_disposable_income_real',
    'macro_cpi': 'market_cpi',
    'macro_disposable_income_nominal': 'market_disposable_income_nominal',
    'macro_household_debt': 'market_household_debt',
    'macro_rpi': 'market_rpi',
}


def _make_service(check_type):
    """check_type별 서비스 객체 생성"""

    class MacroService:
        @staticmethod
        def get_layer1_stats(cursor, target_date, now):
            result = {'check': None, 'failed_items': []}

            schedules = get_schedules_by_type(check_type)
            if not schedules:
                result['check'] = {
                    'name': SECTION_TITLES.get(check_type, check_type),
                    'description': '스케줄 없음',
                    'actual': 0, 'expected': None, 'rate': None,
                    'status': 'PENDING', 'check_type': check_type,
                    'categories': [],
                    'us_time': None, 'kr_time': None, 'kr_time_end': None, 'is_dst': False,
                }
                return result

            schedule = schedules[0]
            is_target = check_target_date(schedule, target_date)
            target_date_str = target_date.strftime('%Y-%m-%d')

            actual = 0
            status = 'PENDING'

            if is_target:
                table_name = _TABLE_MAP.get(check_type)
                if table_name:
                    try:
                        cursor.execute("SAVEPOINT macro_check")
                        actual = repo.get_macro_collection_count(cursor, table_name, target_date_str)
                        cursor.execute("RELEASE SAVEPOINT macro_check")
                    except Exception:
                        cursor.execute("ROLLBACK TO SAVEPOINT macro_check")
                        actual = 0

                status = 'OK' if actual > 0 else 'WARNING'

            macro_info = get_schedule_kst_info(check_type, target_date, now)

            schedule_type_labels = {
                'daily': '매일', 'weekly': '매주', 'monthly': '매월',
                'quarterly': '분기별', 'yearly': '연간',
            }

            next_target = None
            if not is_target:
                next_target = _get_next_target_date(schedule, target_date)

            check = {
                'name': SECTION_TITLES.get(check_type, check_type),
                'description': f'{actual:,}건 수집' if is_target else '분석대상일 아님',
                'actual': actual,
                'expected': None,
                'rate': None,
                'status': status,
                'check_type': check_type,
                'schedule_label': schedule_type_labels.get(schedule.get('schedule_type'), ''),
                'next_target_date': str(next_target) if next_target else None,
                'categories': [],
                'us_time': None,
                'kr_time': None,
                'kr_time_end': None,
                'is_dst': False,
            }

            if macro_info:
                check['us_time'] = f'{target_date} {macro_info["us_start_hour"]:02d}:00'
                check['kr_time'] = macro_info['kst_start']['full_display']
                check['kr_time_end'] = macro_info['kst_end']['full_display']
                check['is_dst'] = macro_info['kst_start']['is_dst']

            result['check'] = check
            return result

    return MacroService()


def get_macro_raw_data(check_type, target_date):
    """Macro 원본 데이터 조회"""
    table_name = _TABLE_MAP.get(check_type)
    if not table_name:
        return {'columns': [], 'data': [], 'total_count': 0}

    target_date_str = target_date.strftime('%Y-%m-%d')
    from apps.common.db import dx_connection
    with dx_connection() as (conn, cursor):
        columns, rows = repo.get_macro_raw_data(cursor, table_name, target_date_str)

    return {
        'check_type': check_type,
        'date': target_date_str,
        'columns': columns,
        'data': rows,
        'total_count': len(rows),
    }


macro_capital_stock_svc = _make_service('macro_capital_stock')
macro_net_interest_svc = _make_service('macro_net_interest')
macro_potential_gdp_svc = _make_service('macro_potential_gdp')
macro_gdp_ppp_nominal_svc = _make_service('macro_gdp_ppp_nominal')
macro_gdp_ppp_real_svc = _make_service('macro_gdp_ppp_real')
macro_disposable_income_real_svc = _make_service('macro_disposable_income_real')
macro_cpi_svc = _make_service('macro_cpi')
macro_disposable_income_nominal_svc = _make_service('macro_disposable_income_nominal')
macro_household_debt_svc = _make_service('macro_household_debt')
macro_rpi_svc = _make_service('macro_rpi')
