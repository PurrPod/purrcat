#!/bin/bash
cd "$(dirname "$0")/.."
echo "Starting PurrCat..."
echo "=========================================="

eval "$(conda shell.bash hook)"
conda activate PurrCat

echo "Starting PurrCat TUI..."
echo "=========================================="
echo "Press [Ctrl+C] to close TUI."
echo "=========================================="
python main.py "$@"