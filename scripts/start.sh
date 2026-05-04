#!/bin/bash
cd "$(dirname "$0")/.."
echo "Starting PurrCat..."
echo "=========================================="

echo "Starting PurrCat TUI..."
echo "=========================================="
echo "Press [Ctrl+C] to close TUI."
echo "=========================================="
conda run --no-capture-output -n PurrCat python main.py "$@"