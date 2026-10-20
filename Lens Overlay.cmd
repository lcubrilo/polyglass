@echo off
rem Starts Lens Overlay in the background (tray icon). First run: setup.cmd
cd /d "%~dp0"
start "" "%USERPROFILE%\.venvs\lens-overlay\Scripts\pythonw.exe" -m lensoverlay
