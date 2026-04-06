#!/bin/bash

echo "🚀 正在启动 CatInCup..."
echo "=========================================="

eval "$(conda shell.bash hook)"
conda activate CatInCup

# 启动后端
echo "🐍 启动 Python 后端服务..."
python backend.py &
BACKEND_PID=$!

# 启动前端
echo "⚛️ 启动 Next.js 前端服务..."
cd ui
npm run dev &
FRONTEND_PID=$!
cd ..

echo "=========================================="
echo "🌟 服务已成功挂载在后台运行！"
echo "🛑 按下 [Ctrl+C] 即可同时安全退出所有服务。"

# 捕获 Ctrl+C，清理进程
trap "echo -e '\n正在关闭 CatInCup 服务...'; kill $BACKEND_PID $FRONTEND_PID; exit" INT
wait