@echo off
title HealthAI - QuickSight localhost
cd /d "%~dp0"
echo ===================================================
echo   QuickSight: SSO login (account 711560820682)
echo ===================================================
aws sso login --profile onedatasoftware-customer-poc
if errorlevel 1 (
  echo SSO login failed. Fix AWS CLI SSL or run login manually, then start server.
  pause
  exit /b 1
)
echo.
echo Starting server at http://localhost:8000
start /b cmd /c "timeout /t 2 >nul && start http://localhost:8000"
python server.py
pause
