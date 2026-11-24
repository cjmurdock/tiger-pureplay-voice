@echo off
REM Update Tiger to the latest version from GitHub.
REM Your settings (config.json), Pureplay pairing (token.json) and speech model are kept.
cd /d "%~dp0"
title Tiger updater
python tiger.py --update
echo.
pause
