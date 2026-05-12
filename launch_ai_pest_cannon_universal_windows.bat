@echo off
cd /d "%USERPROFILE%\ai-pest-cannon"
call "%USERPROFILE%\ai-pest-cannon\yolo-env\Scripts\activate.bat"
set PATH=C:\Program Files\VideoLAN\VLC;%PATH%
python ai_pest_cannon_universal_v1.py
pause
