@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
cd /d "%~dp0"

set COMMAND=%1
shift

set ARGS=
:collect_args
if "%~1"=="" goto execute_command
set ARGS=%ARGS% %1
shift
goto collect_args

:execute_command
if "%COMMAND%"=="setup" (
    call "scripts\setup.bat" %ARGS%
) else if "%COMMAND%"=="start" (
    call "scripts\start.bat" %ARGS%
) else if "%COMMAND%"=="init" (
    python "scripts\cli.py" init %ARGS%
) else if "%COMMAND%"=="env" (
    python "scripts\cli.py" env %ARGS%
) else (
    echo PurrCat CLI - Cross-platform AI Agent Framework
    echo ==========================================
    echo Usage: purrcat ^<command^> [options]
    echo.
    echo Available commands:
    echo   setup   - Initialize environment (Conda, Docker, models, etc.)
    echo   init    - Generate .purrcat configuration files
    echo   start   - Start PurrCat (supports --headless flag)
    echo   env     - Show environment variable reference
    echo.
    echo Examples:
    echo   purrcat setup
    echo   purrcat init
    echo   purrcat start --headless
    echo.
)