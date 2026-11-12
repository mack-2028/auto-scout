@echo off
cd /d "%~dp0"
echo Installing the AI part. This is BIG and can take 10 minutes. Only do this when you have a trained model (best.pt).
python -m pip install ultralytics
echo.
echo DONE. You can close this window.
pause
