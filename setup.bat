@echo off
REM One-time setup for Tiger: installs Python packages and downloads the speech model (~40 MB).
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
  echo Python was not found. Install Python 3.10 or newer from python.org and tick "Add python.exe to PATH".
  pause
  exit /b 1
)

echo Installing Python packages...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if errorlevel 1 (
  echo Package install failed.
  pause
  exit /b 1
)

if exist "models\vosk-model-small-en-us-0.15" (
  echo Speech model already present.
) else (
  echo Downloading speech model...
  if not exist models mkdir models
  powershell -NoProfile -Command "Invoke-WebRequest -Uri 'https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip' -OutFile 'models\model.zip'; Expand-Archive -Path 'models\model.zip' -DestinationPath 'models' -Force; Remove-Item 'models\model.zip'"
)

echo.
echo Microphones on this PC:
python tiger.py --list-mics
echo.
echo Setup done. Open "Tiger Settings.bat" to pick your microphone and voice and enter your
echo carry distances. Tiger uses the Windows default microphone until you pick one.
pause
