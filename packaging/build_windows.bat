@echo off
REM ==================================================
REM File: build_windows.bat
REM Description: Build the AI Pest Cannon Windows app using Python Launcher or an explicit interpreter
REM Created: 2026-10-14 17:26 (UTC)
REM Last modified: 2026-10-14 17:26 (UTC)
REM Change log:
REM   2026-10-14 17:26 - Initial creation, following the ComSim app build kits.
REM ==================================================

setlocal
cd /d "%~dp0"
if defined PEST_PYTHON (
    "%PEST_PYTHON%" build.py %*
) else (
    where py >nul 2>nul
    if errorlevel 1 (
        python build.py %*
    ) else (
        py -3.11 -c "import sys" >nul 2>nul
        if errorlevel 1 (
            py -3 build.py %*
        ) else (
            py -3.11 build.py %*
        )
    )
)
if errorlevel 1 (
    echo Build failed. Read the error above and the build log.
    pause
    exit /b 1
)
pause
endlocal
