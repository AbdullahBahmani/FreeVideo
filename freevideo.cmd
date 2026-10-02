@echo off
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0freevideo.ps1" %*
exit /b %ERRORLEVEL%
