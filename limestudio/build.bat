@echo off
REM Build the Lime Studio desktop app (Windows) inside a virtualenv.
REM Produces dist\LimeStudio\LimeStudio.exe
cd /d "%~dp0"

echo Setting up build virtualenv (.venv)...
python -m venv .venv || goto :err
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip >nul

echo Installing core dependencies...
python -m pip install -r requirements.txt pyinstaller pillow || goto :err

echo Installing optional mic features (numpy, pyaudio)...
python -m pip install -r requirements-optional.txt || echo   Optional audio deps skipped - app will run in simulator mode.

echo Generating icon...
python generate_icon.py || goto :err

echo Building with PyInstaller...
python -m PyInstaller --noconfirm --clean LimeStudio.spec || goto :err

echo.
echo Built dist\LimeStudio\LimeStudio.exe
goto :eof

:err
echo Build failed.
exit /b 1
