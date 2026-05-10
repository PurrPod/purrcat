@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
cd /d "%~dp0.."
echo Welcome to PurrCat environment setup (Windows)...
echo ==========================================

:: 1. Check Docker status
echo Checking Docker service...
docker info >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo Error: Docker not detected or service not running. Please open Docker Desktop.
    pause
    exit /b 1
)
echo Docker engine is running.
echo ==========================================

:: 2. Interactive Sandbox & Network Prompt
echo ==========================================
echo [Sandbox Config] Do you want a lightweight sandbox or a full sandbox? The full docker includes a browser, ffmpeg.
echo 1. Lightweight Sandbox (No browser/ffmpeg, faster to build)
echo 2. Full Sandbox (Includes Chromium, ffmpeg, etc.)
set SANDBOX_CHOICE=1
set /p SANDBOX_CHOICE="Enter 1 or 2 (Default is 1): "

:: Assume lightweight uses Dockerfile.light, full uses Dockerfile.full
set DOCKERFILE_NAME=Dockerfile.light
if "%SANDBOX_CHOICE%"=="2" set DOCKERFILE_NAME=Dockerfile.full

echo ==========================================
echo [Network Config] Are you available to the external network?
echo 1. Yes (Global / Official Source)
echo 2. No (China Region / Aliyun Mirror)
set MIRROR_CHOICE=1
set /p MIRROR_CHOICE="Enter 1 or 2 (Default is 1): "

set BUILD_ARG_APT=deb.debian.org
if "%MIRROR_CHOICE%"=="2" set BUILD_ARG_APT=mirrors.aliyun.com
echo ==========================================

:: 3. Build Agent sandbox (Docker)
echo Building Docker sandbox image using %BUILD_ARG_APT% and %DOCKERFILE_NAME%...
echo Note: First pull may take a few minutes, please wait...

:: Core modification: Use -f to specify the corresponding Dockerfile
docker build -f %DOCKERFILE_NAME% -t my_agent_env:latest --build-arg APT_MIRROR="%BUILD_ARG_APT%" .

if %ERRORLEVEL% neq 0 (
    echo.
    echo Error: Docker image build failed!
    echo Common causes and solutions:
    echo   1. Network issues - Check your proxy or try the other mirror.
    echo   2. Docker Desktop disk space insufficient.
    echo   3. Not logged into Docker Hub, or anonymous pull limit reached.
    echo.
    echo Please fix the environment and run the script again.
    pause
    exit /b 1
)
echo Docker image built successfully!
echo ==========================================

:: 4. Configure Python backend environment (Conda)
echo Configuring PurrCat Conda environment...
call conda env update -f environment.yml --prune
if %ERRORLEVEL% neq 0 (
    echo Environment update failed or not exists, trying to create...
    call conda env create -f environment.yml
    if %ERRORLEVEL% neq 0 (
        echo Conda environment setup failed! Please ensure Conda is installed and in PATH, or check network.
        pause
        exit /b 1
    )
)
echo Conda environment configured successfully!
echo ==========================================

:: 5. Download Embedding model
echo Downloading Embedding model...
call conda run -n PurrCat python "scripts\setup_emb.py"
if %ERRORLEVEL% neq 0 (
    echo Embedding model download failed!
    pause
    exit /b 1
)
echo Model resources ready!
echo ==========================================
echo Congratulations! PurrCat environment is ready.
echo Next: Run 'purrcat start' to start the project.
