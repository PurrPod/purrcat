@echo off
cd /d "%~dp0"
:: 使用 uv run 隐式调用环境，小白再也不用 activate 了
uv run python -m scripts.cli.main %*