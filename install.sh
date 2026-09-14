#!/usr/bin/env bash
# PurrCat one-line installer (source mode)
# Usage: curl -fsSL https://raw.githubusercontent.com/PurrPod/purrcat/main/install.sh | bash
# Auto-installs missing prerequisites (git / uv / Node.js 18+ / Docker / embedding model)
# and registers a global `purrcat` command.
set -euo pipefail

REPO_URL="https://github.com/PurrPod/purrcat.git"
INSTALL_DIR="${PURRCAT_HOME:-$HOME/purrcat}"
BIN_DIR="$HOME/.local/bin"

info() { printf '[*] %s\n' "$*"; }
ok()   { printf '[+] %s\n' "$*"; }
warn() { printf '[!] %s\n' "$*"; }
fail() { printf '[x] %s\n' "$*" >&2; exit 1; }

command -v curl >/dev/null 2>&1 || fail "curl not found; please install it and retry"

SUDO=""
if [ "$(id -u)" -ne 0 ] 2>/dev/null && command -v sudo >/dev/null 2>&1; then
  SUDO="sudo"
fi

is_mac() { [[ "$OSTYPE" == darwin* ]]; }

# Detect distro package manager (macOS uses brew)
detect_pkgmgr() {
  for m in apt-get dnf yum pacman zypper apk; do
    command -v "$m" >/dev/null 2>&1 && { echo "$m"; return; }
  done
  echo ""
}

require_root() {
  if [ "$(id -u)" -ne 0 ] && [ -z "$SUDO" ]; then
    fail "Installing system packages requires root: run as root or install sudo first"
  fi
}

# ---------- git ----------
ensure_git() {
  if command -v git >/dev/null 2>&1; then
    info "git detected: $(git --version)"
    return
  fi
  info "Installing git ..."
  if is_mac; then
    if command -v brew >/dev/null 2>&1; then
      brew install git || fail "brew failed to install git; install it manually: https://git-scm.com/downloads"
    else
      xcode-select --install || true
      fail "Xcode Command Line Tools installation triggered (includes git); re-run this script after it completes"
    fi
  else
    case "$(detect_pkgmgr)" in
      apt-get) require_root; $SUDO apt-get update -qq || true; $SUDO apt-get install -y git || fail "apt-get failed to install git; install it manually: https://git-scm.com/downloads" ;;
      dnf)     require_root; $SUDO dnf install -y git || fail "dnf failed to install git; install it manually: https://git-scm.com/downloads" ;;
      yum)     require_root; $SUDO yum install -y git || fail "yum failed to install git; install it manually: https://git-scm.com/downloads" ;;
      pacman)  require_root; $SUDO pacman -S --noconfirm git || fail "pacman failed to install git; install it manually: https://git-scm.com/downloads" ;;
      zypper)  require_root; $SUDO zypper install -y git || fail "zypper failed to install git; install it manually: https://git-scm.com/downloads" ;;
      apk)     require_root; $SUDO apk add git || fail "apk failed to install git; install it manually: https://git-scm.com/downloads" ;;
      "") fail "No supported package manager found; install git manually: https://git-scm.com/downloads" ;;
    esac
  fi
  command -v git >/dev/null 2>&1 || fail "git installation failed; install it manually: https://git-scm.com/downloads"
  ok "git installed: $(git --version)"
}

# ---------- uv ----------
install_uv_from_github() {
  # Fallback: uv from GitHub releases when astral.sh is unreachable
  local arch libc asset
  case "$(uname -m)" in
    x86_64|amd64)  arch=x86_64 ;;
    aarch64|arm64) arch=aarch64 ;;
    *) return 1 ;;
  esac
  if is_mac; then
    asset="uv-${arch}-apple-darwin.tar.gz"
  else
    libc="gnu"
    ldd --version 2>/dev/null | grep -qi musl && libc="musl"
    asset="uv-${arch}-unknown-linux-${libc}.tar.gz"
  fi
  info "Downloading uv from GitHub releases ..."
  mkdir -p "$BIN_DIR"
  curl -fsSL "https://github.com/astral-sh/uv/releases/latest/download/${asset}" \
    | tar xz -C "$BIN_DIR" --strip-components 1
}

ensure_uv() {
  if command -v uv >/dev/null 2>&1; then
    info "uv detected: $(command -v uv)"
    return
  fi
  info "Installing uv ..."
  if ! curl -LsSf https://astral.sh/uv/install.sh | sh; then
    warn "official uv installer failed; falling back to GitHub releases ..."
  fi
  if ! command -v uv >/dev/null 2>&1; then
    install_uv_from_github || warn "GitHub fallback failed too"
  fi
  command -v uv >/dev/null 2>&1 || fail "uv installation failed; install it manually: https://docs.astral.sh/uv/getting-started/installation/"
  ok "uv installed"
}

# ---------- Node.js 18+ ----------
node_version_ok() {
  command -v node >/dev/null 2>&1 || return 1
  [ "$(node -v | sed 's/^v//' | cut -d. -f1)" -ge 18 ] 2>/dev/null
}

ensure_node() {
  if node_version_ok; then
    info "Node.js detected: $(node -v)"
    return
  fi
  if command -v node >/dev/null 2>&1; then
    warn "Node.js too old ($(node -v), need 18+); installing a newer version ..."
  else
    info "Installing Node.js LTS ..."
  fi
  if is_mac; then
    command -v brew >/dev/null 2>&1 || fail "Homebrew is required; install it first: https://brew.sh"
    brew install node || fail "brew failed to install Node.js; install it manually: https://nodejs.org/"
  else
    case "$(detect_pkgmgr)" in
      apt-get)
        require_root
        # distro nodejs packages are usually too old; use NodeSource LTS
        curl -fsSL https://deb.nodesource.com/setup_lts.x | $SUDO bash - \
          || fail "NodeSource setup failed; check your network or install Node.js manually: https://nodejs.org/"
        $SUDO apt-get install -y nodejs \
          || fail "apt-get failed to install Node.js; install an 18+ version manually: https://nodejs.org/"
        ;;
      dnf|yum)
        require_root
        curl -fsSL https://rpm.nodesource.com/setup_lts.x | $SUDO bash - \
          || fail "NodeSource setup failed; check your network or install Node.js manually: https://nodejs.org/"
        $SUDO dnf install -y nodejs || $SUDO yum install -y nodejs \
          || fail "failed to install Node.js; install an 18+ version manually: https://nodejs.org/"
        ;;
      pacman)  require_root; $SUDO pacman -S --noconfirm nodejs npm || fail "pacman failed to install Node.js; install an 18+ version manually: https://nodejs.org/" ;;
      zypper)  require_root; $SUDO zypper install -y nodejs npm || fail "zypper failed to install Node.js; install an 18+ version manually: https://nodejs.org/" ;;
      apk)      require_root; $SUDO apk add nodejs npm || fail "apk failed to install Node.js; install an 18+ version manually: https://nodejs.org/" ;;
      "") fail "No supported package manager found; install Node.js 18+ manually: https://nodejs.org/" ;;
    esac
  fi
  node_version_ok || fail "Node.js installation failed; install an 18+ version manually: https://nodejs.org/"
  ok "Node.js installed: $(node -v)"
}

# ---------- Docker (failure is non-fatal; retry later from the app's Deploy page) ----------
docker_fail_hint() {
  warn "Docker installation failed — PurrCat itself is fine, but the sandboxed Bash tool requires it."
  warn "Retry later from the app's Config Center -> Deploy page, or install manually: https://docs.docker.com/get-docker/"
}

ensure_docker() {
  if command -v docker >/dev/null 2>&1; then
    info "Docker detected: $(docker --version)"
    return
  fi
  info "Installing Docker ..."
  if is_mac; then
    if command -v brew >/dev/null 2>&1 && brew install --cask docker; then
      open -a Docker 2>/dev/null || true
      ok "Docker Desktop installed (finish first-run setup in the window that opens)"
    else
      docker_fail_hint
    fi
  else
    if curl -fsSL https://get.docker.com | $SUDO sh; then
      $SUDO systemctl enable --now docker 2>/dev/null || true
      $SUDO usermod -aG docker "$USER" 2>/dev/null || true
      ok "Docker installed ($USER added to the docker group; re-login to use it without sudo)"
    else
      docker_fail_hint
    fi
  fi
}

# ---------- Embedding model (follows app logic: skip while data root unconfigured) ----------
ensure_embedding() {
  info "Checking embedding model ..."
  ( cd "$INSTALL_DIR" && uv run python - <<'PYEOF'
import time
from src.utils.embedding_setup import (
    EMBEDDING_DIR,
    _downloading_flag,
    _model_exists,
    ensure_embedding_model,
)

if _model_exists(EMBEDDING_DIR):
    print("[+] Embedding model already present")
else:
    ensure_embedding_model()
    while _downloading_flag.is_set():
        time.sleep(1)
    if _model_exists(EMBEDDING_DIR):
        print("[+] Embedding model downloaded")
    else:
        print("[*] Embedding model not downloaded yet (auto-downloads after first-run data-root setup, or later from Config Center -> Deploy)")
PYEOF
  ) || warn "Embedding model check failed (non-fatal; retry later from the app's Config Center -> Deploy page)"
}

# ---- 1. Prerequisites ----
ensure_git

# Ensure ~/.local/bin is in PATH (for the current process and future shells).
# Must run BEFORE ensure_uv: the uv installer puts the binary there, and on fresh
# systems the current shell's PATH does not include it yet.
case ":$PATH:" in
  *":$BIN_DIR:"*) ;;
  *)
    for rc in "$HOME/.profile" "$HOME/.bashrc" "$HOME/.zshrc"; do
      if [ -f "$rc" ] && ! grep -q '.local/bin' "$rc"; then
        printf '\nexport PATH="$HOME/.local/bin:$PATH"\n' >> "$rc"
        info "Added ~/.local/bin to $rc"
      fi
    done
    ;;
esac
export PATH="$BIN_DIR:$PATH"

ensure_uv
ensure_node

# ---- 2. Fetch source ----
if [ -d "$INSTALL_DIR/.git" ]; then
  info "Existing source detected at $INSTALL_DIR, pulling latest ..."
  git -C "$INSTALL_DIR" pull --ff-only || fail "git pull failed; check local changes and retry"
elif [ -e "$INSTALL_DIR" ]; then
  fail "Directory exists but is not a PurrCat repo: $INSTALL_DIR"
else
  info "Cloning PurrCat source to $INSTALL_DIR ..."
  git clone --depth 1 "$REPO_URL" "$INSTALL_DIR" || fail "git clone failed; check your network"
fi

# ---- 3. Dependencies ----
info "Syncing Python dependencies (uv sync) ..."
( cd "$INSTALL_DIR" && uv sync ) || fail "uv sync failed"

info "Installing desktop dependencies (npm install) ..."
( cd "$INSTALL_DIR" && npm install ) || fail "npm install failed"

info "Installing frontend dependencies (npm install --prefix ui) ..."
( cd "$INSTALL_DIR" && npm install --prefix ui ) || fail "npm install --prefix ui failed"

# ---- 4. Embedding model / Docker ----
ensure_embedding
ensure_docker

# ---- 5. Register purrcat command ----
mkdir -p "$BIN_DIR"
cat > "$BIN_DIR/purrcat" <<'EOF'
#!/usr/bin/env bash
# PurrCat CLI launcher
PURRCAT_HOME="${PURRCAT_HOME:-$HOME/purrcat}"
cd "$PURRCAT_HOME" || { echo "[x] PurrCat source directory not found: $PURRCAT_HOME" >&2; exit 1; }
exec uv run python -m scripts.cli.main "$@"
EOF
chmod +x "$BIN_DIR/purrcat"

# ---- 6. Done ----
echo ""
ok "PurrCat installed successfully!"
echo ""
echo "  Source location:  $INSTALL_DIR"
echo "  Command location: $BIN_DIR/purrcat"
echo ""
echo "Next steps:"
echo "  1. Reopen your terminal (to apply PATH)"
echo "  2. Start the desktop app:   purrcat desktop start"
echo "  3. Update source anytime:   purrcat desktop update"
echo ""
echo "(The sandbox image auto-pulls on backend start; all other components are managed in the app's Config Center -> Deploy page)"
