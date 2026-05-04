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
    echo PurrCat CLI - 跨平台 AI Agent 框架
    echo ==========================================
    echo 用法: purrcat ^<command^> [options]
    echo.
    echo 可用命令:
    echo   setup   - 一键初始化环境 (Conda, Docker, 模型等)
    echo   init    - 生成 .purrcat 配置文件
    echo   start   - 启动 PurrCat (支持追加 --headless)
    echo   env     - 查看环境变量参考
    echo.
    echo 示例:
    echo   purrcat setup
    echo   purrcat init
    echo   purrcat start --headless
    echo.
)