"""
DS Layer 1 — 파일서버 API
"""

from django.http import JsonResponse
from datetime import datetime, timedelta
from apps.common.response import log_error
from apps.common.targets import load_monitoring_targets, get_retailer_map
from config.config import FILE_SERVER_CONFIG
import json
import re
import paramiko


def get_monitoring_targets():
    return load_monitoring_targets()


def get_directory_size(sftp, path):
    """SFTP로 디렉토리 용량 조회 (바이트)"""
    total_size = 0
    try:
        for entry in sftp.listdir_attr(path):
            entry_path = f"{path}/{entry.filename}"
            if entry.st_mode & 0o40000:  # 디렉토리인 경우
                total_size += get_directory_size(sftp, entry_path)
            else:
                total_size += entry.st_size
    except Exception:
        pass
    return total_size


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


def _validate_path_segment(value, label):
    """경로 세그먼트 검증 — Path Traversal 방지"""
    if not value or not _SAFE_NAME.match(value):
        return JsonResponse({'error': f'잘못된 {label}입니다.'}, status=400)
    return None


def _connect_fileserver_sftp():
    transport = paramiko.Transport((FILE_SERVER_CONFIG['host'], FILE_SERVER_CONFIG['port']))
    transport.connect(
        username=FILE_SERVER_CONFIG['username'],
        password=FILE_SERVER_CONFIG['password']
    )
    return transport, paramiko.SFTPClient.from_transport(transport)


def fileserver_stats(request):
    """파일서버 날짜별 용량 조회 API - SFTP 직접 조회"""
    date_str = request.GET.get('date')

    if date_str:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    else:
        target_date = (datetime.now() - timedelta(days=1)).date()

    date_folder = target_date.strftime('%Y%m%d')

    data = {
        'timestamp': datetime.now().isoformat(),
        'date': str(target_date),
        'date_folder': date_folder,
        'countries': [],
        'summary': {}
    }

    try:
        # 파일서버 연결
        transport = paramiko.Transport((FILE_SERVER_CONFIG['host'], FILE_SERVER_CONFIG['port']))
        transport.connect(
            username=FILE_SERVER_CONFIG['username'],
            password=FILE_SERVER_CONFIG['password']
        )
        sftp = paramiko.SFTPClient.from_transport(transport)

        base_path = FILE_SERVER_CONFIG['upload_path']
        total_size = 0
        total_files = 0
        countries_data = []

        # 국가별 디렉토리 조회
        try:
            country_dirs = sftp.listdir(base_path)
        except Exception:
            country_dirs = []

        retailer_map = get_retailer_map()

        for country_code in sorted(country_dirs):
            country_path = f"{base_path}/{country_code}"

            # 디렉토리인지 확인
            try:
                stat = sftp.stat(country_path)
                if not (stat.st_mode & 0o40000):
                    continue
            except Exception:
                continue

            # 해당 날짜 폴더 확인
            date_path = f"{country_path}/{date_folder}"
            try:
                sftp.stat(date_path)
            except FileNotFoundError:
                continue

            # 파일 목록 및 용량 조회 (zip 파일만)
            try:
                files = sftp.listdir_attr(date_path)
                zip_files = [f for f in files if f.filename.endswith('.zip') and not (f.st_mode & 0o40000)]

                for f in sorted(zip_files, key=lambda x: x.filename):
                    filename = f.filename
                    parts = filename.replace('.zip', '').split('_')
                    if len(parts) >= 4:
                        file_country = parts[2]
                        file_retailer = '_'.join(parts[3:])
                        retailer_key = f"{file_country}_{file_retailer}"
                        retailer_name = retailer_map.get(retailer_key, file_retailer)
                    else:
                        retailer_name = country_code.upper()

                    file_modified = datetime.fromtimestamp(f.st_mtime).strftime('%Y-%m-%d %H:%M:%S')

                    total_size += f.st_size
                    total_files += 1

                    countries_data.append({
                        'country_code': country_code,
                        'retailer': retailer_name,
                        'path': date_path,
                        'file_count': 1,
                        'size': f.st_size,
                        'files': [{
                            'name': f.filename,
                            'size': f.st_size,
                            'modified': file_modified
                        }]
                    })
            except Exception:
                continue

        sftp.close()
        transport.close()

        # 수집현황과 동일한 순서로 정렬
        targets = get_monitoring_targets()
        def normalize_name(name):
            return name.lower().replace('-', '').replace('_', '')

        retailer_order = {normalize_name(t[1]): idx for idx, t in enumerate(targets)}

        def get_sort_key(item):
            retailer_name = normalize_name(item.get('retailer', ''))
            return retailer_order.get(retailer_name, 999)

        countries_data.sort(key=get_sort_key)

        unique_countries = set(item['country_code'] for item in countries_data)

        data['countries'] = countries_data
        data['summary'] = {
            'total_countries': len(unique_countries),
            'total_files': total_files,
            'total_size': total_size
        }

    except Exception as e:
        data['error'] = log_error(e)
        data['summary'] = {
            'total_countries': 0,
            'total_files': 0,
            'total_size': 0
        }

    return JsonResponse(data)


def fileserver_browse(request):
    """파일서버 탐색 API — 특정 국가의 날짜 폴더 + backup 폴더 리스팅
    - country 없으면 국가 목록만 반환
    - country 있으면 해당 국가의 날짜 폴더 + backup 폴더 파일 리스팅
    """
    date_str = request.GET.get('date')
    country = request.GET.get('country', '').strip()

    base_path = FILE_SERVER_CONFIG['upload_path']

    # country 없으면 국가 목록만 반환 (모니터링 대상 국가만)
    if not country:
        transport, sftp = None, None
        try:
            targets = get_monitoring_targets()
            active_countries = set(t[4] for t in targets if t[4])  # country 컬럼

            transport, sftp = _connect_fileserver_sftp()
            entries = sftp.listdir_attr(base_path)
            countries = []
            for e in sorted(entries, key=lambda x: x.filename):
                if not (e.st_mode & 0o40000):
                    continue
                if e.filename not in active_countries:
                    continue
                countries.append({
                    'name': e.filename,
                    'modified': datetime.fromtimestamp(e.st_mtime).strftime('%Y-%m-%d %H:%M:%S'),
                })
            return JsonResponse({'countries': countries})
        except Exception as e:
            return JsonResponse({'error': log_error(e)}, status=500)
        finally:
            if sftp: sftp.close()
            if transport: transport.close()

    # Path Traversal 방지
    err = _validate_path_segment(country, '국가 코드')
    if err: return err

    # country 있으면 날짜 폴더 + backup 폴더 리스팅
    today = datetime.now().date()
    if date_str:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        if target_date > today:
            target_date = today
    else:
        target_date = (datetime.now() - timedelta(days=1)).date()

    date_folder = target_date.strftime('%Y%m%d')
    country_path = f"{base_path}/{country}"

    def list_files(sftp, dir_path, prefix=None):
        """디렉토리의 파일 목록 반환. prefix 지정 시 해당 접두사로 시작하는 파일만."""
        result = []
        try:
            files = sftp.listdir_attr(dir_path)
        except FileNotFoundError:
            return result
        except Exception:
            return result

        for f in sorted(files, key=lambda x: x.filename):
            if f.st_mode & 0o40000:
                continue
            if prefix and not f.filename.startswith(prefix):
                continue
            result.append({
                'name': f.filename,
                'size': f.st_size,
                'modified': datetime.fromtimestamp(f.st_mtime).strftime('%Y-%m-%d %H:%M:%S'),
            })
        return result

    transport, sftp = None, None
    try:
        transport, sftp = _connect_fileserver_sftp()

        # 국가 디렉토리 존재 확인
        try:
            sftp.stat(country_path)
        except FileNotFoundError:
            return JsonResponse({'error': f'국가 폴더 "{country}"를 찾을 수 없습니다.'}, status=404)

        date_files = list_files(sftp, f"{country_path}/{date_folder}")
        backup_files = list_files(sftp, f"{country_path}/backup", prefix=date_folder)

        return JsonResponse({
            'date': str(target_date),
            'date_folder': date_folder,
            'country': country,
            'date_files': date_files,
            'backup_files': backup_files,
        })

    except Exception as e:
        return JsonResponse({'error': log_error(e)}, status=500)
    finally:
        if sftp: sftp.close()
        if transport: transport.close()


def fileserver_move(request):
    """파일서버 파일 이동 API — 날짜 폴더 → backup 폴더"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST 요청만 허용됩니다.'}, status=405)

    try:
        body = json.loads(request.body)
    except Exception:
        return JsonResponse({'error': '잘못된 요청 형식입니다.'}, status=400)

    country = body.get('country', '').strip()
    date_folder = body.get('date_folder', '').strip()
    files = body.get('files', [])

    if not country or not date_folder or not files:
        return JsonResponse({'error': 'country, date_folder, files가 필요합니다.'}, status=400)

    # Path Traversal 방지
    for label, val in [('국가 코드', country), ('날짜 폴더', date_folder)]:
        err = _validate_path_segment(val, label)
        if err: return err
    for filename in files:
        err = _validate_path_segment(filename, '파일명')
        if err: return err

    base_path = FILE_SERVER_CONFIG['upload_path']
    src_dir = f"{base_path}/{country}/{date_folder}"
    dst_dir = f"{base_path}/{country}/backup"

    transport, sftp = None, None
    try:
        transport, sftp = _connect_fileserver_sftp()

        # backup 폴더 없으면 생성
        try:
            sftp.stat(dst_dir)
        except FileNotFoundError:
            sftp.mkdir(dst_dir)

        moved = []
        failed = []
        skipped = []

        for filename in files:
            src_path = f"{src_dir}/{filename}"
            dst_path = f"{dst_dir}/{filename}"
            try:
                # 대상 파일 존재 여부 확인
                try:
                    sftp.stat(dst_path)
                    skipped.append(filename)
                    continue
                except FileNotFoundError:
                    pass
                sftp.rename(src_path, dst_path)
                moved.append(filename)
            except Exception as e:
                failed.append({'file': filename, 'error': str(e)})

        return JsonResponse({
            'success': len(failed) == 0,
            'moved': moved,
            'failed': failed,
            'skipped': skipped,
        })

    except Exception as e:
        return JsonResponse({'error': log_error(e)}, status=500)
    finally:
        if sftp: sftp.close()
        if transport: transport.close()
