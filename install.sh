#!/usr/bin/env bash
# PurrCat 一键安装脚本（源码模式）
# 用法: curl -fsSL https://raw.githubusercontent.com/PurrPod/purrcat/main/install.sh | bash
# 自动安装缺失的前置依赖: git / uv / Node.js 18+ / Docker / 嵌入模型，并注册全局 purrcat 命令
set -euo pipefail

REPO_URL="https://github.com/PurrPod/purrcat.git"
INSTALL_DIR="${PURRCAT_HOME:-$HOME/purrcat}"
BIN_DIR="$HOME/.local/bin"

info() { printf '[*] %s\n' "$*"; }
ok()   { printf '[+] %s\n' "$*"; }
warn() { printf '[!] %s\n' "$*"; }
fail() { printf '[x] %s\n' "$*" >&2; exit 1; }

command -v curl >/dev/null 2>&1 || fail "未检测到 curl，请先安装后重试"

SUDO=""
if [ "$(id -u)" -ne 0 ] 2>/dev/null && command -v sudo >/dev/null 2>&1; then
  SUDO="sudo"
fi

is_mac() { [[ "$OSTYPE" == darwin* ]]; }

# 探测发行版包管理器（macOS 走 brew）
detect_pkgmgr() {
  for m in apt-get dnf yum pacman zypper apk; do
    command -v "$m" >/dev/null 2>&1 && { echo "$m"; return; }
  done
  echo ""
}

require_root() {
  if [ "$(id -u)" -ne 0 ] && [ -z "$SUDO" ]; then
    fail "安装系统包需要 root 权限：请以 root 运行，或先安装 sudo"
  fi
}

# ---------- git ----------
ensure_git() {
  if command -v git >/dev/null 2>&1; then
    info "已检测到 git: $(git --version)"
    return
  fi
  info "安装 git ..."
  if is_mac; then
    if command -v brew >/dev/null 2>&1; then
      brew install git || fail "brew 安装 git 失败，请手动安装: https://git-scm.com/downloads"
    else
      xcode-select --install || true
      fail "已触发 Xcode Command Line Tools 安装（含 git），完成后请重新运行本脚本"
    fi
  else
    case "$(detect_pkgmgr)" in
      apt-get) require_root; $SUDO apt-get update -qq; $SUDO apt-get install -y git ;;
      dnf)     require_root; $SUDO dnf install -y git ;;
      yum)     require_root; $SUDO yum install -y git ;;
      pacman)  require_root; $SUDO pacman -S --noconfirm git ;;
      zypper)  require_root; $SUDO zypper install -y git ;;
      apk)     require_root; $SUDO apk add git ;;
      "") fail "未识别到包管理器，请手动安装 git: https://git-scm.com/downloads" ;;
    esac
  fi
  command -v git >/dev/null 2>&1 || fail "git 安装失败，请手动安装: https://git-scm.com/downloads"
  ok "git 安装完成: $(git --version)"
}

# ---------- uv ----------
ensure_uv() {
  if command -v uv >/dev/null 2>&1; then
    info "已检测到 uv: $(command -v uv)"
    return
  fi
  info "安装 uv 包管理器 ..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  command -v uv >/dev/null 2>&1 || fail "uv 安装失败，请手动执行: curl -LsSf https://astral.sh/uv/install.sh | sh"
  ok "uv 安装完成"
}

# ---------- Node.js 18+ ----------
node_version_ok() {
  command -v node >/dev/null 2>&1 || return 1
  [ "$(node -v | sed 's/^v//' | cut -d. -f1)" -ge 18 ] 2>/dev/null
}

ensure_node() {
  if node_version_ok; then
    info "已检测到 Node.js: $(node -v)"
    return
  fi
  if command -v node >/dev/null 2>&1; then
    warn "Node.js 版本过低（$(node -v)，需 18+），安装新版 ..."
  else
    info "安装 Node.js LTS ..."
  fi
  if is_mac; then
    command -v brew >/dev/null 2>&1 || fail "请先安装 Homebrew 后重试: https://brew.sh"
    brew install node || fail "brew 安装 Node.js 失败，请手动安装: https://nodejs.org/"
  else
    case "$(detect_pkgmgr)" in
      apt-get)
        require_root
        # 发行版源自带的 nodejs 普遍过旧，走 NodeSource LTS
        curl -fsSL https://deb.nodesource.com/setup_lts.x | $SUDO bash -
        $SUDO apt-get install -y nodejs
        ;;
      dnf|yum)
        require_root
        curl -fsSL https://rpm.nodesource.com/setup_lts.x | $SUDO bash -
        $SUDO dnf install -y nodejs || $SUDO yum install -y nodejs
        ;;
      pacman)  require_root; $SUDO pacman -S --noconfirm nodejs npm ;;
      zypper)  require_root; $SUDO zypper install -y nodejs npm ;;
      apk)      require_root; $SUDO apk add nodejs npm ;;
      "") fail "未识别到包管理器，请手动安装 Node.js 18+: https://nodejs.org/" ;;
    esac
  fi
  node_version_ok || fail "Node.js 安装失败，请手动安装 18+ 版本: https://nodejs.org/"
  ok "Node.js 安装完成: $(node -v)"
}

# ---------- Docker（失败仅警告，可稍后在应用内「部署」页重试）----------
docker_fail_hint() {
  warn "Docker 安装失败——不影响 PurrCat 本体安装，但沙盒 Bash 工具依赖它。"
  warn "可稍后在应用内 配置中心 → 部署 页重试，或手动安装: https://docs.docker.com/get-docker/"
}

ensure_docker() {
  if command -v docker >/dev/null 2>&1; then
    info "已检测到 Docker: $(docker --version)"
    return
  fi
  info "安装 Docker ..."
  if is_mac; then
    if command -v brew >/dev/null 2>&1 && brew install --cask docker; then
      open -a Docker 2>/dev/null || true
      ok "Docker Desktop 安装完成（请在弹出的窗口中完成首次设置）"
    else
      docker_fail_hint
    fi
  else
    if curl -fsSL https://get.docker.com | $SUDO sh; then
      $SUDO systemctl enable --now docker 2>/dev/null || true
      $SUDO usermod -aG docker "$USER" 2>/dev/null || true
      ok "Docker 安装完成（已将 $USER 加入 docker 组，重新登录后免 sudo 使用）"
    else
      docker_fail_hint
    fi
  fi
}

# ---------- 嵌入模型（遵循应用逻辑：数据盘未配置时跳过，首启后自动下载）----------
ensure_embedding() {
  info "检查嵌入模型 (embedding model) ..."
  ( cd "$INSTALL_DIR" && uv run python - <<'PYEOF'
import time
from src.utils.embedding_setup import (
    EMBEDDING_DIR,
    _downloading_flag,
    _model_exists,
    ensure_embedding_model,
)

if _model_exists(EMBEDDING_DIR):
    print("[+] 嵌入模型已存在")
else:
    ensure_embedding_model()
    while _downloading_flag.is_set():
        time.sleep(1)
    if _model_exists(EMBEDDING_DIR):
        print("[+] 嵌入模型下载完成")
    else:
        print("[*] 嵌入模型暂未下载（首次启动完成数据盘配置后会自动下载，或稍后在配置中心「部署」页安装）")
PYEOF
  ) || warn "嵌入模型检查失败（不影响安装，稍后可在应用内 配置中心 → 部署 页安装）"
}

# ---- 1. 前置依赖 ----
ensure_git
ensure_uv

# 确保 ~/.local/bin 在 PATH（对当前进程与未来终端均生效）
case ":$PATH:" in
  *":$BIN_DIR:"*) ;;
  *)
    for rc in "$HOME/.profile" "$HOME/.bashrc" "$HOME/.zshrc"; do
      if [ -f "$rc" ] && ! grep -q '.local/bin' "$rc"; then
        printf '\nexport PATH="$HOME/.local/bin:$PATH"\n' >> "$rc"
        info "已将 ~/.local/bin 加入 $rc"
      fi
    done
    ;;
esac
export PATH="$BIN_DIR:$PATH"

ensure_node

# ---- 2. 获取源码 ----
if [ -d "$INSTALL_DIR/.git" ]; then
  info "检测到已有源码: $INSTALL_DIR，拉取最新..."
  git -C "$INSTALL_DIR" pull --ff-only || fail "git pull 失败，请检查本地改动后重试"
elif [ -e "$INSTALL_DIR" ]; then
  fail "目录已存在且不是 PurrCat 仓库: $INSTALL_DIR"
else
  info "克隆 PurrCat 源码到 $INSTALL_DIR ..."
  git clone --depth 1 "$REPO_URL" "$INSTALL_DIR"
fi

# ---- 3. 安装依赖 ----
info "同步 Python 依赖 (uv sync) ..."
( cd "$INSTALL_DIR" && uv sync )

info "安装桌面端依赖 (npm install) ..."
( cd "$INSTALL_DIR" && npm install )

info "安装前端依赖 (npm install --prefix ui) ..."
( cd "$INSTALL_DIR" && npm install --prefix ui )

# ---- 4. 嵌入模型 / Docker ----
ensure_embedding
ensure_docker

# ---- 5. 生成 purrcat 命令 ----
mkdir -p "$BIN_DIR"
cat > "$BIN_DIR/purrcat" <<'EOF'
#!/usr/bin/env bash
# PurrCat CLI launcher
PURRCAT_HOME="${PURRCAT_HOME:-$HOME/purrcat}"
cd "$PURRCAT_HOME" || { echo "[x] PurrCat 源码目录不存在: $PURRCAT_HOME" >&2; exit 1; }
exec uv run python -m scripts.cli.main "$@"
EOF
chmod +x "$BIN_DIR/purrcat"

# ---- 6. 完成 ----
echo ""
ok "PurrCat 安装完成!"
echo ""
echo "  源码位置:  $INSTALL_DIR"
echo "  命令位置:  $BIN_DIR/purrcat"
echo ""
echo "下一步:"
echo "  1. 重新打开终端（使 PATH 生效）"
echo "  2. 启动桌面端:    purrcat desktop start"
echo "  3. 日常更新源码:  purrcat desktop update"
echo ""
echo "（沙盒镜像会在后端启动时自动拉取；其余组件均可在应用内 配置中心 → 部署 页管理）"
