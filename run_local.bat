@echo off
title HealthAI Server Starter
echo ===================================================
echo   Starting HealthAI - Healthcare Analytics Platform
echo   Backend: Flask (python server.py)
echo   Frontend: http://localhost:8000
echo ===================================================
echo.

:: Launch the browser to localhost:8000 in 2 seconds
start /b cmd /c "timeout /t 2 >nul && start http://localhost:8000"

:: Start the python server
python server.py

pause
