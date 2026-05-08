#!/bin/bash
cd "$(dirname "$0")/.."
echo "Starting PurrCat..."
echo "Press [Ctrl+C] to safely close."
conda run --no-capture-output -n PurrCat python main.py "$@"