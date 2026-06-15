@echo off
echo Starting Face Recognition System...

:: Automatically navigate to the exact folder where this batch file lives
cd /d "%~dp0"

:: Start the Flask server in a new window
start "FaceRec Server" cmd /k python server.py

:: Wait 3 seconds to give the server time to start before launching the camera
timeout /t 3 /nobreak > nul

:: Start the main camera script in a new window
start "FaceRec Main" cmd /k python main.py