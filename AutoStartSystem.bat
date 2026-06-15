@echo off
cd /d "%~dp0"

:: Start the Flask server invisibly in the background
start "" pythonw server.py

:: Wait 3 seconds to give the server time to start
timeout /t 3 /nobreak > nul

:: Start the main camera script invisibly in the background
start "" pythonw main.py