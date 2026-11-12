@echo off
cd /d "%~dp0"
set /p T=Type a time in the video when a match is starting, like 1:23:40 and press Enter: 
python pick_zones.py config.json %T%
pause
