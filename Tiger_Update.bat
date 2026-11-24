@echo off
title Tiger updater
REM One-time updater for Tiger copies from before 24 November 2026 (no Updates tab yet).
REM Double-click it from anywhere, for example your Downloads folder. It downloads the newest
REM Tiger from https://github.com/cjmurdock/tiger-pureplay-voice, finds your Tiger folder,
REM keeps your settings (config.json), Pureplay pairing (token.json) and speech model, and
REM updates everything else. Afterwards, use the Updates tab in Tiger Settings instead.
setlocal
set "WORK=%TEMP%\tiger-update-%RANDOM%%RANDOM%"
set "ZIP=%WORK%\tiger.zip"
where python >nul 2>nul
if errorlevel 1 (
  echo Python was not found. Tiger needs Python - see the setup guide. Nothing was changed.
  goto done
)
where curl >nul 2>nul
if errorlevel 1 (
  echo This updater needs Windows 10 or newer. Nothing was changed.
  goto done
)
mkdir "%WORK%"
echo Downloading the newest Tiger from GitHub...
curl -fsSL -o "%ZIP%" https://github.com/cjmurdock/tiger-pureplay-voice/archive/refs/heads/main.zip
if errorlevel 1 (
  echo The download did not work. Check the internet connection. Nothing was changed.
  goto cleanup
)
tar -xf "%ZIP%" -C "%WORK%"
if errorlevel 1 (
  echo Could not unpack the download. Nothing was changed.
  goto cleanup
)
python "%WORK%\tiger-pureplay-voice-main\tiger.py" --update --find --hint "%~dp0." --from-zip "%ZIP%"
:cleanup
rmdir /s /q "%WORK%" 2>nul
:done
echo.
pause
