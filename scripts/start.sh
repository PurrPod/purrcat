#!/bin/bash
cd "$(dirname "$0")/.."
echo "🚀 正在启动 CatInCup..."
echo "=========================================="

eval "$(conda shell.bash hook)"
conda activate CatInCup

# 启动 TUI 界面
echo "🐍 启动 CatInCup TUI..."
echo "=========================================="
echo "🛑 按下 [Ctrl+C] 即可关闭 TUI。"
echo "=========================================="
python main.py