#!/bin/bash
# 遇到错误立即退出
set -e
cd "$(dirname "$0")/.."
echo "🐱 欢迎安装 PurrCat 环境 (macOS / Linux)..."
echo "=========================================="

# 1. 检查基础依赖
echo "🔍 检查系统依赖..."
command -v conda >/dev/null 2>&1 || { echo >&2 "❌ 未找到 conda，请先安装 Miniconda 或 Anaconda。"; exit 1; }
command -v docker >/dev/null 2>&1 || { echo >&2 "❌ 未找到 docker，请先安装 Docker。"; exit 1; }
echo "✅ 基础依赖检查通过！"

# 2. 构建沙盒并自动换源
echo "📦 正在构建 Docker 沙盒镜像..."
if docker build -t my_agent_env:latest .; then
    echo "✅ [官方源] Docker 沙盒镜像构建成功！"
elif docker build -t my_agent_env:latest --build-arg REGISTRY=docker.1panel.live/library/ .; then
    echo "✅ [加速源 1] Docker 沙盒镜像构建成功！"
elif docker build -t my_agent_env:latest --build-arg REGISTRY=dockerpull.com/library/ .; then
    echo "✅ [加速源 2] Docker 沙盒镜像构建成功！"
elif docker build -t my_agent_env:latest --build-arg REGISTRY=m.daocloud.io/docker.io/library/ .; then
    echo "✅ [加速源 3] Docker 沙盒镜像构建成功！"
else
    echo "❌ 灾难性错误：所有已知镜像源均尝试失败！请检查网络连接。"
    exit 1
fi

# 3. 配置 Python 后端环境
echo "🐍 正在配置 Conda 环境..."
eval "$(conda shell.bash hook)"
if conda info --envs | grep -q 'PurrCat'; then
    echo "⚠️ 环境已存在，尝试更新..."
    conda env update -f environment.yml --prune
else
    conda env create -f environment.yml
fi
echo "✅ Conda 环境配置完成！"



echo "=========================================="

# 4. 下载 Embedding 模型
echo "📥 正在下载 Embedding 模型到本地..."
python "$(dirname "$0")/setup_emb.py"
if [ $? -ne 0 ]; then
    echo "❌ Embedding 模型下载失败！"
    exit 1
fi
echo "✅ Embedding 模型准备完成！"

echo "=========================================="
echo "🎉 部署完成！PurrCat 已经准备就绪。"
echo "👉 请运行 ./start.sh 来启动项目。"