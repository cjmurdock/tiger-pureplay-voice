@echo off
REM Open the Tiger Settings window: voice, microphone, club distances and status.
cd /d "%~dp0"
where pythonw >nul 2>nul
if errorlevel 1 (
  python tiger.py --settings
  if errorlevel 1 pause
) else (
  start "" pythonw tiger.py --settings
)
