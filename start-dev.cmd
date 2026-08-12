@echo off
setlocal

rem Double-clickable launcher. Windows commonly opens .ps1 files in an editor,
rem so this wrapper explicitly invokes Windows PowerShell and forwards options.
cd /d "%~dp0"
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-dev.ps1" %*

if errorlevel 1 (
    echo.
    echo Startup failed. Review the message above.
    pause
    exit /b 1
)

endlocal
