@echo off
call venv\Scripts\activate.bat
echo.
echo  CCTV Intelligence is starting...
echo  Local:    http://localhost:8000
echo  LAN:      http://%COMPUTERNAME%:8000   (or your IP - run 'ipconfig')
echo.
echo  Press Ctrl+C to stop.
echo.
python -m uvicorn app.server:app --host 0.0.0.0 --port 8000
pause
