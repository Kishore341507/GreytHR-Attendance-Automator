@echo off
title GreytHR Attendance Automator Setup
cd /d "%~dp0"

echo ===================================================
echo     GreytHR Attendance Automator Setup & Start
echo ===================================================
echo.

:: Check if Python is installed
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in PATH!
    echo Please install Python 3.9+ from python.org and check "Add Python to PATH".
    pause
    exit /b 1
)

:: Create virtual environment if not exists
if not exist "venv" (
    echo [1/4] Creating Python virtual environment...
    python -m venv venv
) else (
    echo [1/4] Virtual environment already exists.
)

:: Upgrade pip and install dependencies
echo [2/4] Installing required Python libraries...
call venv\Scripts\python.exe -m pip install --upgrade pip >nul 2>&1
call venv\Scripts\pip.exe install playwright pystray Pillow

:: Install Playwright Chromium browser
echo [3/4] Installing Playwright Chromium browser...
call venv\Scripts\playwright.exe install chromium

:: Add shortcut to Windows Startup folder for auto-start on PC boot
echo [4/4] Configuring Windows Auto-Start...
set "STARTUP_FOLDER=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "SHORTCUT_PATH=%STARTUP_FOLDER%\GreytHR_Attendance.lnk"
set "TARGET_VBS=%~dp0run_silent.vbs"

powershell -Command "$s=(New-Object -COM WScript.Shell).CreateShortcut('%SHORTCUT_PATH%'); $s.TargetPath='wscript.exe'; $s.Arguments='\"%TARGET_VBS%\" \"%~dp0\"'; $s.WorkingDirectory='%~dp0'; $s.Save()"

echo.
echo ===================================================
echo   Setup Complete! Starting Attendance Manager...
echo ===================================================
echo.

:: Start silently in background
wscript.exe "%~dp0run_silent.vbs" "%~dp0"

echo GreytHR Attendance Manager is now running in the background system tray!
echo Look for the icon in your Windows Taskbar tray.
echo.
pause
