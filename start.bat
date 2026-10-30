@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Откройте http://127.0.0.1:8765 в браузере.
echo Для остановки нажмите Ctrl+C в этом окне.
python server.py
pause
