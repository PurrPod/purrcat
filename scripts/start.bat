@echo off
chcp 65001 >nul
cd /d "%~dp0.."
echo Starting PurrCat...
echo Press [Ctrl+C] to safely close.
conda run --no-capture-output -n PurrCat python main.py %*
pause