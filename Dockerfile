# 1. 使用官方的 Python 3.10 镜像 (基于 Debian)
# 它内部已经完美配置好了 python3 和 pip，无需再通过 apt 安装
FROM python:3.10-slim

# 2. 设置环境变量
ENV DEBIAN_FRONTEND=noninteractive

# 3. 只需安装极少量的基础工具包
# 加入 --no-install-recommends 可以防止安装不必要的推荐包，进一步加快速度
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    vim \
    && rm -rf /var/lib/apt/lists/*

# 4. 设置工作目录
WORKDIR /agent_vm

# 5. 维持容器存活
CMD ["sleep", "infinity"]