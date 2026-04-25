@echo off
chcp 65001 >nul
cd /d "%~dp0.."
echo 🚀 正在启动 PurrCat...
echo ==========================================

:: 启动 TUI 界面
echo 🐍 正在启动 PurrCat TUI...
echo ==========================================
echo 🛑 关闭说明：
echo    在当前窗口按 [Ctrl+C] 即可关闭 TUI
echo ==========================================
call conda activate PurrCat && python main.py

:: Prevent terminal from closing automatically when program crashes
pause