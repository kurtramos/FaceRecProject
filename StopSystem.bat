@echo off
echo Shutting down 1Rotary AI and Server...
taskkill /F /IM python.exe /T
echo System Offline.
timeout /t 2 > NUL