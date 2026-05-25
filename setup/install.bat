@echo off
echo ============================================
echo   Nexus News Agent - Startup Installer
echo ============================================
echo.

:: Get the Python path
for /f "tokens=*" %%i in ('where python') do set PYTHON_PATH=%%i

:: Get the scheduler script path
set SCRIPT_PATH=%~dp0..\src\core\scheduler.py
set SCRIPT_PATH=%SCRIPT_PATH:\setup\..\=%

:: Convert to absolute path
pushd %~dp0..
set PROJECT_PATH=%CD%
popd

set SCHEDULER_PATH=%PROJECT_PATH%\src\core\scheduler.py

echo Python path: %PYTHON_PATH%
echo Script path: %SCHEDULER_PATH%
echo.

:: Delete existing task if it exists
schtasks /delete /tn "NexusNewsAgent" /f >nul 2>&1

:: Create new Task Scheduler task
schtasks /create ^
    /tn "NexusNewsAgent" ^
    /tr "\"%PYTHON_PATH%\" \"%SCHEDULER_PATH%\"" ^
    /sc ONLOGON ^
    /delay 0000:30 ^
    /rl HIGHEST ^
    /f

if %ERRORLEVEL% == 0 (
    echo.
    echo ============================================
    echo   SUCCESS! News Agent will now auto-launch
    echo   every time you log into Windows.
    echo ============================================
    echo.
    echo The agent will:
    echo   - Wait 4 minutes after login
    echo   - Check internet connection
    echo   - Fetch and summarize latest news
    echo   - Open the Nexus News window
    echo.
) else (
    echo.
    echo ERROR: Failed to create task.
    echo Try running this file as Administrator.
    echo.
)

pause