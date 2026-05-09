@echo off
REM CCTV Intelligence (web) - one-time setup for Windows.
REM Requires Python 3.10 or 3.11 on PATH.

echo Creating virtual environment...
python -m venv venv
if errorlevel 1 goto :error

call venv\Scripts\activate.bat

echo Upgrading pip...
python -m pip install --upgrade pip

echo Installing requirements (large download - PyTorch + EasyOCR)...
pip install -r requirements.txt
if errorlevel 1 goto :error

if not exist models mkdir models

echo Downloading YOLOv8n weights...
if not exist models\yolov8n.pt (
    python -c "from ultralytics import YOLO; YOLO('yolov8n.pt')"
    if exist yolov8n.pt move yolov8n.pt models\yolov8n.pt >nul
)

echo Downloading license plate detector...
if not exist models\license_plate_detector.pt (
    powershell -Command "Invoke-WebRequest -Uri 'https://github.com/Muhammad-Zeerak-Khan/Automatic-License-Plate-Recognition-using-YOLOv8/raw/main/license_plate_detector.pt' -OutFile 'models\license_plate_detector.pt'"
)

echo.
echo ============================================
echo   Setup complete!
echo ============================================
echo.
echo NEXT:
echo   1. Drop test videos in videos\ named sample1.mp4, sample2.mp4, sample3.mp4
echo   2. Edit config\config.json - set sender_app_password to your Gmail App Password
echo   3. Run: run.bat
echo   4. Open in browser: http://localhost:8000
echo.
goto :eof

:error
echo Setup failed.
pause
exit /b 1
