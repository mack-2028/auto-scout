@echo off
cd /d "%~dp0"
python auto_scout.py config.json
echo.
echo DONE. Results are in results.json
pause
