@echo off
cd /d "%~dp0"
python -m pip install -r requirements-ai.txt
if errorlevel 1 (
 echo Gagal memasang dependensi AI. Periksa koneksi internet/Python, atau jalankan run.bat untuk mode sinyal.
 pause
 exit /b 1
)
start "" powershell -NoProfile -Command "Start-Sleep -Seconds 3; Start-Process http://127.0.0.1:8000"
python -m uvicorn app:app --host 127.0.0.1 --port 8000
pause
