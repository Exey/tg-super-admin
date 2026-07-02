@echo off
REM Build TG Admin Tools for Windows: one-file .exe + one-dir bundle.
cd /d "%~dp0\.."

set NAME=TgAdminTools

where python >nul 2>nul
if errorlevel 1 (
    echo Python not found. Install Python 3.10+ from python.org and check "Add to PATH".
    pause & exit /b 1
)

if not exist .venv-build python -m venv .venv-build
call .venv-build\Scripts\activate.bat
pip install -U pip
pip install -r requirements.txt pyinstaller

REM Variant 1: single .exe
pyinstaller --noconfirm --clean --windowed --onefile ^
    --name %NAME% --distpath dist\onefile main.py

REM Variant 2: one-dir bundle (starts faster)
pyinstaller --noconfirm --clean --windowed ^
    --name %NAME% --distpath dist\onedir main.py

echo.
echo Done:
echo    dist\onefile\%NAME%.exe
echo    dist\onedir\%NAME%\%NAME%.exe
pause
