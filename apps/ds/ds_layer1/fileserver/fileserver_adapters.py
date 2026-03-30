import paramiko
from config.config import FILE_SERVER_CONFIG

class FileServerAdapter:
    """
    SFTP를 이용한 파일서버 통신을 전담하는 Adapter 클래스입니다.
    비즈니스 로직(Service 계층)에서는 paramiko 모듈에 직접 의존하지 않고 이 클래스를 사용합니다.
    """
    def __init__(self):
        self.transport = None
        self.sftp = None
        self.base_path = FILE_SERVER_CONFIG['upload_path']

    def __enter__(self):
        self.transport = paramiko.Transport((FILE_SERVER_CONFIG['host'], FILE_SERVER_CONFIG['port']))
        self.transport.connect(
            username=FILE_SERVER_CONFIG['username'],
            password=FILE_SERVER_CONFIG['password']
        )
        self.sftp = paramiko.SFTPClient.from_transport(self.transport)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.sftp:
            self.sftp.close()
        if self.transport:
            self.transport.close()

    def get_country_dirs(self):
        """base_path 내부의 모든 국가 디렉토리 목록 반환"""
        try:
            return self.sftp.listdir(self.base_path)
        except Exception:
            return []

    def get_zip_files(self, country_code, date_folder):
        """특정 국가의 특정 날짜 폴더에 있는 zip 파일들의 정보를 추출"""
        country_path = f"{self.base_path}/{country_code}"
        date_path = f"{country_path}/{date_folder}"
        results = []
        try:
            if not (self.sftp.stat(country_path).st_mode & 0o40000):
                return results, date_path
            self.sftp.stat(date_path)
            files = self.sftp.listdir_attr(date_path)
            for f in files:
                if f.filename.endswith('.zip') and not (f.st_mode & 0o40000):
                    results.append({
                        'filename': f.filename,
                        'size': f.st_size,
                        'mtime': f.st_mtime
                    })
        except Exception:
            pass
        return results, date_path
    
    def get_active_countries(self, active_countries_set):
        """활성화된 모니터링 대상 국가들의 폴더 정보만 필터링하여 반환"""
        try:
            entries = self.sftp.listdir_attr(self.base_path)
            countries = []
            for e in sorted(entries, key=lambda x: x.filename):
                if not (e.st_mode & 0o40000):
                    continue
                if e.filename not in active_countries_set:
                    continue
                countries.append({
                    'name': e.filename,
                    'mtime': e.st_mtime
                })
            return countries
        except Exception:
            return []

    def check_country_exists(self, country):
        try:
            self.sftp.stat(f"{self.base_path}/{country}")
            return True
        except FileNotFoundError:
            return False

    def list_files(self, country_code, sub_folder, prefix=None):
        """지정된 하위 폴더의 파일 정보 리스트를 반환"""
        dir_path = f"{self.base_path}/{country_code}/{sub_folder}" if sub_folder else f"{self.base_path}/{country_code}"
        result = []
        try:
            files = self.sftp.listdir_attr(dir_path)
            for f in sorted(files, key=lambda x: x.filename):
                if f.st_mode & 0o40000:
                    continue
                if prefix and not f.filename.startswith(prefix):
                    continue
                result.append({
                    'name': f.filename,
                    'size': f.st_size,
                    'mtime': f.st_mtime
                })
        except Exception:
            pass
        return result

    def move_files_to_backup(self, country, date_folder, files):
        """날짜 폴더에서 backup 폴더로 파일들을 이동 (rename)"""
        src_dir = f"{self.base_path}/{country}/{date_folder}"
        dst_dir = f"{self.base_path}/{country}/backup"
        
        try:
            self.sftp.stat(dst_dir)
        except Exception:
            # backup 디렉토리가 없으면 생성
            self.sftp.mkdir(dst_dir)
            
        moved, failed, skipped = [], [], []
        for filename in files:
            src_path = f"{src_dir}/{filename}"
            dst_path = f"{dst_dir}/{filename}"
            try:
                # 목적지에 동일 파일명 존재 여부 확인
                try:
                    self.sftp.stat(dst_path)
                    skipped.append(filename)
                    continue
                except FileNotFoundError:
                    pass
                
                self.sftp.rename(src_path, dst_path)
                moved.append(filename)
            except Exception as e:
                failed.append({'file': filename, 'error': str(e)})
                
        return moved, failed, skipped
