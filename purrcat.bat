@echo off
cd /d "%~dp0"
uv run python -m scripts.cli.main %*