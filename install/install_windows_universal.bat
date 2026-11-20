@echo off
setlocal

echo AI Pest Cannon Universal - Windows installer

set APP_DIR=%USERPROFILE%\ai-pest-cannon
set VENV_DIR=%APP_DIR%\yolo-env
set APP_FILE=ai_pest_cannon.py
set LAUNCHER=%APP_DIR%\launch_ai_pest_cannon_universal_windows.bat

mkdir "%APP_DIR%" 2>nul
cd /d "%APP_DIR%"

echo.
echo This installer deletes and recreates the venv: %VENV_DIR%
echo It installs PyTorch CUDA 12.6 for older NVIDIA GPUs such as GTX 1060.
echo.
set /p CONFIRM=Continue? [y/N] 
if /I not "%CONFIRM%"=="y" goto :cancel

if exist "%VENV_DIR%" (
  echo Removing old venv...
  rmdir /s /q "%VENV_DIR%"
)

py -3.11 -m venv "%VENV_DIR%"
if errorlevel 1 (
  echo Failed to create venv with py -3.11. Install 64-bit Python 3.11 and try again.
  pause
  exit /b 1
)

call "%VENV_DIR%\Scripts\activate.bat"
python -m pip install --upgrade pip setuptools wheel

python -m pip install --index-url https://download.pytorch.org/whl/cu126 torch==2.6.0+cu126 torchvision==0.21.0+cu126 torchaudio==2.6.0+cu126
python -m pip install numpy==1.26.4
python -m pip install PySide6 opencv-python paho-mqtt ultralytics python-vlc
python -m pip install --force-reinstall numpy==1.26.4

(
  echo @echo off
  echo cd /d "%%USERPROFILE%%\ai-pest-cannon"
  echo call "%%USERPROFILE%%\ai-pest-cannon\yolo-env\Scripts\activate.bat"
  echo set PATH=C:\Program Files\VideoLAN\VLC;%%PATH%%
  echo python ai_pest_cannon.py
  echo pause
) > "%LAUNCHER%"

echo.
echo Testing installation...
python -c "import torch, numpy; print('torch:', torch.__version__); print('torch cuda:', torch.version.cuda); print('numpy:', numpy.__version__); print('cuda available:', torch.cuda.is_available()); print('device:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'none')"

echo.
echo Install complete.
echo Copy ai_pest_cannon.py into: %APP_DIR%
echo Launch with: %LAUNCHER%
echo.
echo Make sure 64-bit VLC is installed. If VLC is not in C:\Program Files\VideoLAN\VLC, edit the launcher PATH line.
pause
exit /b 0

:cancel
echo Cancelled.
pause
exit /b 0
