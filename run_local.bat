@echo off
chcp 65001 >nul
cd /d %~dp0
echo ==========================================
echo  5단계 방어 체계 모니터링 시스템 (로컬)
echo ==========================================
echo.
echo 서버 시작 중...
echo 브라우저에서 http://localhost:5050 접속
echo 종료: Ctrl+C
echo.
python manage.py runserver 127.0.0.1:5050
pause
