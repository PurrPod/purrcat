@echo off
setlocal enabledelayedexpansion
:: 设置控制台为 UTF-8 编码，防止中文乱码
chcp 65001 >nul
cd /d "%~dp0.."
echo 🐱 欢迎安装 CatInCup 环境 (Windows 自动构建版)...
echo ==========================================

:: 1. 自动检测与安装基础依赖
echo 🔍 检查并补全系统依赖...

:: 检测并安装 Node.js
where npm >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo ⚠️ 未检测到 Node.js，正在自动下载安装包...
    :: 下载 Node.js 20 LTS 版本的 MSI 安装包
    curl -o nodejs_setup.msi "https://nodejs.org/dist/v20.12.2/node-v20.12.2-x64.msi"
    echo ⏳ 正在静默安装 Node.js，请稍候...
    :: /qn 表示静默安装，/norestart 表示不自动重启
    start /wait msiexec /i nodejs_setup.msi /qn /norestart
    del nodejs_setup.msi
    :: 将 Node.js 临时加入当前运行环境的变量中，防止后续 npm 找不到
    set "PATH=%PATH%;C:\Program Files\nodejs"
    echo ✅ Node.js 安装完成！
) else (
    echo ✅ Node.js 已安装。
)

:: 检测并安装 Miniconda
where conda >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo ⚠️ 未检测到 Conda，正在自动下载 Miniconda3...
    curl -o miniconda_setup.exe "https://repo.anaconda.com/miniconda/Miniconda3-latest-Windows-x86_64.exe"
    echo ⏳ 正在静默安装 Miniconda3，可能需要1-3分钟，请耐心等待...
    :: /S 表示静默安装，/RegisterPython=0 不设为系统默认，安装到用户目录
    start /wait "" miniconda_setup.exe /InstallationType=JustMe /RegisterPython=0 /S /D=%USERPROFILE%\Miniconda3
    del miniconda_setup.exe
    :: 将 Conda 临时加入当前变量
    set "PATH=%PATH%;%USERPROFILE%\Miniconda3\condabin;%USERPROFILE%\Miniconda3\Scripts"
    echo ✅ Miniconda 安装完成！
) else (
    echo ✅ Conda 已安装。
)

:: 检测 Docker (Docker 无法简单的静默安装，只能提示用户手动处理)
where docker >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo ❌ 未检测到 Docker！
    echo Docker Desktop 需要依赖操作系统的虚拟化（WSL2/Hyper-V），无法一键安全安装。
    echo 请前往 https://www.docker.com/products/docker-desktop/ 手动下载并启动。
    pause
    exit /b 1
) else (
    echo ✅ Docker 已安装并配置。
)

echo ==========================================

:: 2. 构建 Agent 本地沙盒 (Docker)
echo 📦 正在构建 Docker 沙盒镜像...
set BUILD_SUCCESS=0

echo [1/4] 正在尝试官方 Docker 源拉取镜像...
docker build -t my_agent_env:latest .
if %ERRORLEVEL% equ 0 set BUILD_SUCCESS=1 & goto after_build

echo ⚠️ 官方源超时，[2/4] 自动切换至国内加速源 (1Panel)...
docker build -t my_agent_env:latest --build-arg REGISTRY=docker.1panel.live/library/ .
if %ERRORLEVEL% equ 0 set BUILD_SUCCESS=1 & goto after_build

echo ⚠️ 源1失效，[3/4] 自动切换至国内加速源 (DockerPull)...
docker build -t my_agent_env:latest --build-arg REGISTRY=dockerpull.com/library/ .
if %ERRORLEVEL% equ 0 set BUILD_SUCCESS=1 & goto after_build

echo ⚠️ 源2失效，[4/4] 自动切换至国内加速源 (DaoCloud)...
docker build -t my_agent_env:latest --build-arg REGISTRY=m.daocloud.io/docker.io/library/ .
if %ERRORLEVEL% equ 0 set BUILD_SUCCESS=1 & goto after_build

:after_build
if %BUILD_SUCCESS% equ 0 (
    echo ❌ 灾难性错误：所有已知镜像源均尝试失败！
    echo 如果您未打开 Docker 桌面版，请先打开桌面版，如果您打开了桌面版依旧不行，请检查您的网络连接，或开启全局代理后重试。
    pause
    exit /b 1
)
echo ✅ Docker 沙盒镜像构建成功！

:: 3. 配置 Python 后端环境 (Conda)
echo 🐍 正在配置 CatInCup 专属 Conda 环境...
:: 为了确保刚安装的 conda 命令能立即生效，直接调用绝对路径的 conda.bat
call "%USERPROFILE%\Miniconda3\condabin\conda.bat" env create -f environment.yml || call conda env create -f environment.yml
echo ✅ Conda 环境配置完成！

:: 4. 配置 Next.js 前端环境
echo ⚛️ 正在配置前端依赖...
cd ui
call npm install
cd ..
echo ✅ 前端依赖安装完成！

echo ==========================================
echo 🎉 部署大功告成！CatInCup 已经完全准备就绪。
echo 👉 请双击运行 start.bat 来启动项目。
pause