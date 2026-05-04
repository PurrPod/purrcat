@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
cd /d "%~dp0.."
echo 欢迎准备 PurrCat 运行环境 (Windows)...
echo ==========================================

:: 1. 检查 Docker 状态
echo 正在检查 Docker 服务...
docker info >nul 2>&1
if !ERRORLEVEL! neq 0 (
    echo 错误：未检测到 Docker 或服务未启动！请打开 Docker Desktop。
    pause
    exit /b 1
)
echo Docker 引擎运行中。
echo ==========================================

:: 2. 构建 Agent 本地沙盒 (Docker)
echo 正在构建 Docker 沙盒镜像 (my_agent_env:latest)...
echo 首次拉取基础镜像可能需要几分钟，请耐心等待...

docker build -t my_agent_env:latest .
if %ERRORLEVEL% neq 0 (
    echo.
    echo 错误：Docker 镜像构建失败！
    echo 常见原因及解决办法：
    echo   1. 网络问题（国内用户极易遇到拉取超时）。
    echo      建议配置阿里云个人镜像加速器，或开启全局代理。
    echo   2. Docker Desktop 磁盘空间不足或未下载并打开 Docker Desktop
    echo   3. 尚未登录 Docker Hub 或达到匿名拉取限制。
    echo.
    echo 请修复网络或环境后，重新运行此脚本。
    pause
    exit /b 1
)
echo Docker 镜像构建完成！
echo ==========================================

:: 3. 配置 Python 后端环境 (Conda)
echo 正在配置 PurrCat 的 Conda 专属环境...
:: 直接运行命令，如果没有 Conda，原生 cmd 会直接在这里抛出红字报错
call conda env update -f environment.yml --prune
if %ERRORLEVEL! neq 0 (
    echo 环境更新失败或不存在，尝试全新创建...
    call conda env create -f environment.yml
    if !ERRORLEVEL! neq 0 (
        echo Conda 环境配置失败！请确认已安装 Conda 并加入环境变量，或检查网络。
        pause
        exit /b 1
    )
)
echo Conda 环境配置完成！
echo ==========================================

:: 4. 下载 Embedding 模型
echo 正在下载 Embedding 模型...
call conda run -n PurrCat python "scripts\setup_emb.py"
if %ERRORLEVEL% neq 0 (
    echo Embedding 模型预下载失败！
    pause
    exit /b 1
)
echo 模型资源准备就绪！

echo ==========================================
echo 恭喜！PurrCat 运行环境已搭建完毕。
echo 下一步：请运行 'purrcat start' 启动项目。
pause