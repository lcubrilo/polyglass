@echo off
rem One-time setup: creates the Python environment in %USERPROFILE%\.venvs\lens-overlay
cd /d "%~dp0"
python -m venv "%USERPROFILE%\.venvs\lens-overlay" || exit /b 1
"%USERPROFILE%\.venvs\lens-overlay\Scripts\python" -m pip install --upgrade pip
"%USERPROFILE%\.venvs\lens-overlay\Scripts\python" -m pip install -r requirements.txt
