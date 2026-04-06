ARG REGISTRY=""
# 动态拼接镜像源前缀
FROM ${REGISTRY}python:3.10-slim

# 设置环境变量
ENV DEBIAN_FRONTEND=noninteractive

# 只需安装极少量的基础工具包
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    vim \
    && rm -rf /var/lib/apt/lists/*

# 设置工作目录
WORKDIR /agent_vm

# 维持容器存活
CMD ["sleep", "infinity"]