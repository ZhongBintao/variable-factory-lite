@echo off
rem Double-click to run install.ps1 (PowerShell blocks .ps1 files by default; this wrapper allows just this one).
chcp 65001 >nul
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" %*
set RC=%ERRORLEVEL%
if not defined LITE_NO_PAUSE echo %cmdcmdline% | find /i "%~0" >nul && pause
exit /b %RC%
