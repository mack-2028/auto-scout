@echo off
cd /d "%~dp0"
echo Making a fake match video and testing...
python make_test_video.py
python auto_scout.py test_config.json
echo.
echo For team 14623 the right answer is: auto 4, teleop 2, tips 1, parked 1
echo Look in test_results.json to see what it found.
pause
