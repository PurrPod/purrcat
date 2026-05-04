#!/bin/bash
set -e
cd "$(dirname "$0")/.."
echo "Welcome to PurrCat environment setup (macOS / Linux)..."
echo "=========================================="

# 1. Check Docker status
echo "Checking Docker service..."
if ! docker info >/dev/null 2>&1; then
    echo "Error: Docker not installed or daemon not running. Please start Docker and try again."
    exit 1
fi
echo "Docker engine is running."
echo "=========================================="

# 2. Interactive Network Prompt
echo "[Network Config] Choose APT package mirror for Docker container:"
echo "1. Official Source (Global / Default)"
echo "2. Aliyun Mirror (Users in China)"
read -p "Enter 1 or 2 (Default is 1): " MIRROR_CHOICE

BUILD_ARG_APT="deb.debian.org"
if [ "$MIRROR_CHOICE" == "2" ]; then
    BUILD_ARG_APT="mirrors.aliyun.com"
fi
echo "=========================================="

# 3. Build Agent sandbox (Docker)
echo "Building Docker sandbox image using $BUILD_ARG_APT..."
echo "Note: First pull may take a few minutes, please wait..."

set +e # Temporarily disable set -e to capture error
# Pass the temporary argument
docker build -t my_agent_env:latest --build-arg APT_MIRROR="$BUILD_ARG_APT" .
BUILD_STATUS=$?
set -e

if [ $BUILD_STATUS -ne 0 ]; then
    echo ""
    echo "Error: Docker image build failed completely!"
    echo "Common causes:"
    echo "  1. Network issues - Check your proxy or try the other mirror."
    echo "  2. Docker disk space insufficient."
    echo "  3. Not logged into Docker Hub, or anonymous pull limit reached."
    echo "Please fix the environment and try again."
    exit 1
fi
echo "Docker image built successfully!"
echo "=========================================="

# 4. Configure Python backend environment
echo "Configuring PurrCat Conda environment..."
eval "$(conda shell.bash hook)"

if conda info --envs 2>/dev/null | grep -q 'PurrCat'; then
    echo "Environment 'PurrCat' already exists, trying to update dependencies..."
    conda env update -f environment.yml --prune
else
    conda env create -f environment.yml
fi
echo "Conda environment configured successfully!"
echo "=========================================="

# 5. Download Embedding model
echo "Downloading Embedding model..."
conda run -n PurrCat python "scripts/setup_emb.py"
echo "Model resources ready!"
echo "=========================================="

echo "Congratulations! PurrCat environment is ready."
echo "Next: Run './purrcat start' to start the project."