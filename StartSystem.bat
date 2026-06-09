@echo off
:: Start the Local Server
start /b cmd /c "python server.py"

:: Wait 3 seconds
timeout /t 3 /nobreak > NUL

:: Start the Face Recognition AI
start /b cmd /c "python main.py"
exit