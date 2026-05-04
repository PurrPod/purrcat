@echo off
chcp 65001 >nul
cd /d "%~dp0.."
echo Starting PurrCat...
echo ==========================================

echo Starting PurrCat TUI...
echo ==========================================
echo Close instructions:
echo    Press [Ctrl+C] in current window to close TUI
echo ==========================================
call conda activate PurrCat && python main.py %*

pause