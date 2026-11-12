@echo off
cd /d "%~dp0"
echo Installing the basic parts (takes a minute)...
python -m pip install opencv-python yt-dlp
winget install -e --id Gyan.FFmpeg
echo.
echo DONE. You can close this window.
pause
