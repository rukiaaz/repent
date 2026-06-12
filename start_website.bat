@echo off
echo Starting Balance Dashboard...
echo.
echo Starting Bot API Server on port 8000...
start "Bot API" python bot_api.py
timeout /t 3 /nobreak >nul
echo.
echo Starting Flask Website on port 5000...
python website\app.py
pause