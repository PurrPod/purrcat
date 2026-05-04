#!/bin/bash
cd "$(dirname "$0")/.."
echo "正在启动 PurrCat..."
echo "=========================================="

eval "$(conda shell.bash hook)"
conda activate PurrCat

echo "启动 PurrCat TUI..."
echo "=========================================="
echo "按下 [Ctrl+C] 即可关闭 TUI。"
echo "=========================================="
python main.py "$@"