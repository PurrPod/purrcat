#!/usr/bin/env bash
# PurrCat 一键安装脚本（源码模式）
# 用法: curl -fsSL https://raw.githubusercontent.com/PurrPod/purrcat/main/install.sh | bash
set -euo pipefail

REPO_URL="https://github.com/PurrPod/purrcat.git"
INSTALL_DIR="${PURRCAT_HOME:-$HOME/purrcat}"
BIN_DIR="$HOME/.local/bin"

info() { printf '[*] %s\n' "$*"; }
ok()   { printf '[+] %s\n' "$*"; }
fail() { printf '[x] %s\n' "$*" >&2; exit 1; }

# ---- 1. 前置检查: git / Node 18+ ----
command -v git >/dev/null 2>&1 || fail "未检测到 git，请先安装: https://git-scm.com/downloads"

command -v node >/dev/null 2>&1 || fail "未检测到 Node.js（需 18+），请先安装: https://nodejs.org/"
NODE_MAJOR="$(node -v | sed 's/^v//' | cut -d. -f1)"
[ "$NODE_MAJOR" -ge 18 ] 2>/dev/null || fail "Node.js 版本过低（当前 $(node -v)，需 18+），请升级: https://nodejs.org/"

# ---- 2. 安装 uv（若无）----
if command -v uv >/dev/null 2>&1; then
  info "已检测到 uv: $(command -v uv)"
else
  info "安装 uv 包管理器..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi

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
command -v uv >/dev/null 2>&1 || fail "uv 安装失败，请手动执行: curl -LsSf https://astral.sh/uv/install.sh | sh"

# ---- 3. 获取源码 ----
if [ -d "$INSTALL_DIR/.git" ]; then
  info "检测到已有源码: $INSTALL_DIR，拉取最新..."
  git -C "$INSTALL_DIR" pull --ff-only || fail "git pull 失败，请检查本地改动后重试"
elif [ -e "$INSTALL_DIR" ]; then
  fail "目录已存在且不是 PurrCat 仓库: $INSTALL_DIR"
else
  info "克隆 PurrCat 源码到 $INSTALL_DIR ..."
  git clone --depth 1 "$REPO_URL" "$INSTALL_DIR"
fi

# ---- 4. 安装依赖 ----
info "同步 Python 依赖 (uv sync) ..."
( cd "$INSTALL_DIR" && uv sync )

info "安装桌面端依赖 (npm install) ..."
( cd "$INSTALL_DIR" && npm install )

info "安装前端依赖 (npm install --prefix ui) ..."
( cd "$INSTALL_DIR" && npm install --prefix ui )

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
echo "  3. 初始化沙盒:    purrcat setup    （沙盒 Bash 依赖 Docker）"
echo "  4. 日常更新源码:  purrcat desktop update"
