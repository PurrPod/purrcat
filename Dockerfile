ARG REGISTRY=""
FROM ${REGISTRY}python:3.10-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    LANG=C.UTF-8 \
    BUN_INSTALL="/usr/local" \
    PATH="/usr/local/bin:${PATH}"

ARG APT_MIRROR=""
RUN if [ -n "${APT_MIRROR}" ]; then \
        sed -i "s/deb.debian.org/${APT_MIRROR}/g" /etc/apt/sources.list.d/debian.sources 2>/dev/null || \
        sed -i "s/deb.debian.org/${APT_MIRROR}/g" /etc/apt/sources.list 2>/dev/null; \
    fi

# Step 1: Install system-level APT packages (added Chromium and its shared libraries)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    ca-certificates \
    ffmpeg \
    jq \
    unzip \
    zip \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Step 2: Install Node.js (Kept as you had it, in case your other agents need npm/node)
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && npm config set registry https://registry.npmmirror.com \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Step 3: Configure Python environment (fast with PyPI mirror)
RUN pip config set global.index-url https://mirrors.aliyun.com/pypi/simple/ \
    && pip install --no-cache-dir --upgrade pip setuptools wheel

WORKDIR /agent_vm

CMD ["sleep", "infinity"]