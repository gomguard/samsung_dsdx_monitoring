"""
DS Layer 1 — 파일서버 서비스
Adapter 클래스를 활용하여 외부 통신을 배제한 순수 비즈니스 로직
"""

from datetime import datetime
from apps.common.targets import load_monitoring_targets, get_retailer_map
import re
from .fileserver_adapters import FileServerAdapter

def get_monitoring_targets():
    return load_monitoring_targets()

def format_size(size_bytes):
    """바이트를 읽기 쉬운 형식으로 변환"""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"

_SAFE_NAME = re.compile(r'^[a-zA-Z0-9_\-\.]+$')

def validate_path_segment(value, label):
    """경로 세그먼트 검증 — Path Traversal 방지."""
    if not value or not _SAFE_NAME.match(value):
        return f'잘못된 {label}입니다.'
    return None

def get_fileserver_stats(target_date):
    """파일서버 날짜별 용량 조회"""
    date_folder = target_date.strftime('%Y%m%d')
    total_size = 0
    total_files = 0
    countries_data = []

    with FileServerAdapter() as adapter:
        country_dirs = adapter.get_country_dirs()
        retailer_map = get_retailer_map()

        for country_code in sorted(country_dirs):
            files, date_path = adapter.get_zip_files(country_code, date_folder)
            if not files and date_path == "":
                continue

            if not files:
                continue

            for f in sorted(files, key=lambda x: x['filename']):
                filename = f['filename']
                parts = filename.replace('.zip', '').split('_')
                if len(parts) >= 4:
                    file_country = parts[2]
                    file_retailer = '_'.join(parts[3:])
                    retailer_key = f"{file_country}_{file_retailer}"
                    retailer_name = retailer_map.get(retailer_key, file_retailer)
                else:
                    retailer_name = country_code.upper()

                file_modified = datetime.fromtimestamp(f['mtime']).strftime('%Y-%m-%d %H:%M:%S')

                total_size += f['size']
                total_files += 1

                countries_data.append({
                    'country_code': country_code,
                    'retailer': retailer_name,
                    'path': date_path,
                    'file_count': 1,
                    'size': f['size'],
                    'files': [{
                        'name': f['filename'],
                        'size': f['size'],
                        'modified': file_modified
                    }]
                })

    targets = get_monitoring_targets()
    def normalize_name(name):
        return name.lower().replace('-', '').replace('_', '')

    retailer_order = {normalize_name(t[1]): idx for idx, t in enumerate(targets)}

    def get_sort_key(item):
        retailer_name = normalize_name(item.get('retailer', ''))
        return retailer_order.get(retailer_name, 999)

    countries_data.sort(key=get_sort_key)
    unique_countries = set(item['country_code'] for item in countries_data)

    return {
        'date_folder': date_folder,
        'countries': countries_data,
        'summary': {
            'total_countries': len(unique_countries),
            'total_files': total_files,
            'total_size': total_size
        }
    }

def get_country_list():
    """모니터링 대상 국가 목록 조회"""
    targets = get_monitoring_targets()
    active_countries_set = set(t[4] for t in targets if t[4])

    with FileServerAdapter() as adapter:
        countries = adapter.get_active_countries(active_countries_set)

    for c in countries:
        c['modified'] = datetime.fromtimestamp(c['mtime']).strftime('%Y-%m-%d %H:%M:%S')
        del c['mtime']

    return countries

def browse_country_files(country, target_date):
    """특정 국가의 날짜 폴더 + backup 폴더 파일 리스팅"""
    date_folder = target_date.strftime('%Y%m%d')

    with FileServerAdapter() as adapter:
        if not adapter.check_country_exists(country):
            raise FileNotFoundError(f'국가 폴더 "{country}"를 찾을 수 없습니다.')

        date_files = adapter.list_files(country, date_folder)
        backup_files = adapter.list_files(country, "backup", prefix=date_folder)

    for f in date_files:
        f['modified'] = datetime.fromtimestamp(f['mtime']).strftime('%Y-%m-%d %H:%M:%S')
        del f['mtime']
    for f in backup_files:
        f['modified'] = datetime.fromtimestamp(f['mtime']).strftime('%Y-%m-%d %H:%M:%S')
        del f['mtime']

    return {
        'date': str(target_date),
        'date_folder': date_folder,
        'country': country,
        'date_files': date_files,
        'backup_files': backup_files,
    }

def move_files_to_backup(country, date_folder, files):
    """파일서버 파일 이동"""
    with FileServerAdapter() as adapter:
        moved, failed, skipped = adapter.move_files_to_backup(country, date_folder, files)
        
    return {
        'success': len(failed) == 0,
        'moved': moved,
        'failed': failed,
        'skipped': skipped,
    }
