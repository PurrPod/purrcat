@echo off
chcp 65001 >nul
cd /d "%~dp0.."
echo 🚀 正在启动 CatInCup...
echo ==========================================

:: 1. 启动后端 (Python)
echo 🐍 正在新窗口启动 Python 后端服务...
start "CatInCup Backend" cmd /k "call conda activate CatInCup && python backend.py"

:: 2. 启动前端 (Next.js)
echo ⚛️ 正在启动 Next.js 前端服务...
echo ==========================================
echo 🛑 关闭说明：
echo    1. 在当前窗口按 [Ctrl+C] 即可关闭前端
echo    2. 后端请直接点击关闭弹出的 "CatInCup Backend" 窗口
echo ==========================================
cd ui
npm run dev