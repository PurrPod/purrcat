@echo off
chcp 65001 >nul
cd /d "%~dp0.."
echo 🚀 正在启动 CatInCup...
echo ==========================================

:: 1. 启动后端 (Python)
echo 🐍 正在新窗口启动 Python 后端服务...
:: 使用 start 开启新窗口，/k 保证窗口运行后不自动关闭
start "CatInCup Backend" cmd /k "call conda activate CatInCup && python backend.py"

:: 2. 启动前端 (Next.js)
echo ⚛️ 正在新窗口启动 Next.js 前端服务...
cd ui
start "CatInCup Frontend" cmd /k "npm run dev"
cd ..

echo ==========================================
echo 🌟 服务已成功启动！
echo 🛑 如需关闭服务，请直接关闭刚才弹出的两个命令行窗口。
pause