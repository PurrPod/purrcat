#!/bin/bash
set -e
cd "$(dirname "$0")/.."
echo "欢迎准备 PurrCat 运行环境 (macOS / Linux)..."
echo "=========================================="

echo "正在检查 Docker 服务..."
if ! docker info >/dev/null 2>&1; then
    echo "错误：Docker 未安装或守护进程未运行。请启动 Docker 服务后重试。"
    exit 1
fi
echo "Docker 引擎运行中。"
echo "=========================================="

echo "正在构建 Docker 沙盒镜像 (my_agent_env:latest)..."
if docker build -t my_agent_env:latest .; then
    echo "[官方源] Docker 沙盒镜像构建成功！"
elif docker build -t my_agent_env:latest --build-arg REGISTRY=docker.1panel.live/library/ .; then
    echo "[加速源 1] Docker 沙盒镜像构建成功！"
elif docker build -t my_agent_env:latest --build-arg REGISTRY=dockerpull.com/library/ .; then
    echo "[加速源 2] Docker 沙盒镜像构建成功！"
elif docker build -t my_agent_env:latest --build-arg REGISTRY=m.daocloud.io/docker.io/library/ .; then
    echo "[加速源 3] Docker 沙盒镜像构建成功！"
else
    echo "错误：Docker 镜像构建彻底失败！请检查网络连接。"
    exit 1
fi
echo "=========================================="

echo "正在配置 PurrCat 的 Conda 专属环境..."
eval "$(conda shell.bash hook)"

if conda info --envs 2>/dev/null | grep -q 'PurrCat'; then
    echo "环境 'PurrCat' 已存在，正在尝试更新依赖..."
    conda env update -f environment.yml --prune
else
    conda env create -f environment.yml
fi
echo "Conda 环境配置完成！"
echo "=========================================="

echo "正在下载 Embedding 模型..."
conda run -n PurrCat python "scripts/setup_emb.py"
echo "模型资源准备就绪！"

echo "=========================================="
echo "恭喜！PurrCat 运行环境已搭建完毕。"
echo "下一步：请运行 './purrcat start' 启动项目。"