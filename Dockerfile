ARG REGISTRY=""
# 动态拼接镜像源前缀
FROM ${REGISTRY}python:3.10-slim

# 设置环境变量
# PYTHONUNBUFFERED=1: 确保 Python 日志实时输出不被缓冲
# LANG=C.UTF-8: 确保中文环境和文件读写不乱码
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    LANG=C.UTF-8

# 安装基础工具、编译依赖、多媒体及文件处理工具
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    vim \
    ca-certificates \
    build-essential \
    ffmpeg \
    jq \
    unzip \
    zip \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && npm config set registry https://registry.npmmirror.com \
    && pip config set global.index-url https://mirrors.aliyun.com/pypi/simple/ \
    && pip install --no-cache-dir --upgrade pip setuptools wheel \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 设置工作目录
WORKDIR /agent_vm

# 维持容器存活
CMD ["sleep", "infinity"]