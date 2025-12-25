"""
Waitress WSGI 서버 실행 스크립트 (운영용)
- Django 앱을 Waitress로 실행
- Nginx와 연동하여 사용
"""
import os
import sys

# 프로젝트 루트를 path에 추가
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

from waitress import serve
from config.wsgi import application

if __name__ == '__main__':
    print('=' * 50)
    print(' Waitress 서버 시작 (운영 모드)')
    print(' http://127.0.0.1:5050')
    print(' 종료: Ctrl+C')
    print('=' * 50)

    serve(application, host='127.0.0.1', port=5050, threads=4)
