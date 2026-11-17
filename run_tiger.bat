@echo off
REM Start Tiger voice control. Extra options: --type (test by typing), --dry-run, --debug
cd /d "%~dp0"
python tiger.py %*
if errorlevel 1 pause
