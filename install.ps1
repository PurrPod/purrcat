# PurrCat 一键安装脚本（源码模式）
# 用法: irm https://raw.githubusercontent.com/PurrPod/purrcat/main/install.ps1 | iex
# 自动安装缺失的前置依赖: git / uv / Node.js 18+ / Docker Desktop / 嵌入模型，并注册全局 purrcat 命令
$ErrorActionPreference = "Stop"

$RepoUrl    = "https://github.com/PurrPod/purrcat.git"
$InstallDir = if ($env:PURRCAT_HOME) { $env:PURRCAT_HOME } else { "$env:USERPROFILE\purrcat" }
$BinDir     = "$env:USERPROFILE\.local\bin"

function Info($m) { Write-Host "[*] $m" -ForegroundColor Cyan }
function Ok($m)   { Write-Host "[+] $m" -ForegroundColor Green }
function Warn($m) { Write-Host "[!] $m" -ForegroundColor Yellow }
function Fail($m) { throw $m }

# winget 安装完成后刷新当前会话 PATH（注册表已更新，当前进程不会自动生效）
function Update-SessionPath {
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
                [Environment]::GetEnvironmentVariable("Path", "User")
}

function Install-ByWinget($id) {
    Info "（若弹出 UAC 授权窗口请允许）"
    winget install --id $id -e --accept-source-agreements --accept-package-agreements
    return ($LASTEXITCODE -eq 0)
}

# ---------- git ----------
if (Get-Command git -ErrorAction SilentlyContinue) {
    Info "已检测到 git: $(git --version)"
} else {
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        Fail "未检测到 winget，请手动安装 git: https://git-scm.com/download/win"
    }
    Info "安装 git ..."
    $null = Install-ByWinget "Git.Git"
    Update-SessionPath
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        Fail "git 安装失败，请手动安装: https://git-scm.com/download/win"
    }
    Ok "git 安装完成: $(git --version)"
}

# ---------- uv ----------
if (Get-Command uv -ErrorAction SilentlyContinue) {
    Info "已检测到 uv: $(Get-Command uv).Source"
} else {
    Info "安装 uv 包管理器 ..."
    irm https://astral.sh/uv/install.ps1 | iex
}
$env:Path = "$BinDir;$env:Path"
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Fail "uv 安装失败，请手动执行: irm https://astral.sh/uv/install.ps1 | iex"
}

# ---------- Node.js 18+ ----------
$nodeOk = $false
if (Get-Command node -ErrorAction SilentlyContinue) {
    $nodeMajor = [int]((node -v).TrimStart('v').Split('.')[0])
    if ($nodeMajor -ge 18) {
        Info "已检测到 Node.js: $(node -v)"
        $nodeOk = $true
    } else {
        Warn "Node.js 版本过低（当前 $(node -v)，需 18+），请先升级后重试: https://nodejs.org/"
        Fail "Node.js 版本不满足要求"
    }
}
if (-not $nodeOk) {
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        Fail "未检测到 winget，请手动安装 Node.js 18+: https://nodejs.org/"
    }
    Info "安装 Node.js LTS ..."
    $null = Install-ByWinget "OpenJS.NodeJS.LTS"
    Update-SessionPath
    if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
        Fail "Node.js 安装失败，请手动安装 18+ 版本: https://nodejs.org/"
    }
    Ok "Node.js 安装完成: $(node -v)"
}

# ---------- 获取源码 ----------
if (Test-Path "$InstallDir\.git") {
    Info "检测到已有源码: $InstallDir，拉取最新..."
    git -C $InstallDir pull --ff-only
    if ($LASTEXITCODE -ne 0) { Fail "git pull 失败，请检查本地改动后重试" }
} elseif (Test-Path $InstallDir) {
    Fail "目录已存在且不是 PurrCat 仓库: $InstallDir"
} else {
    Info "克隆 PurrCat 源码到 $InstallDir ..."
    git clone --depth 1 $RepoUrl $InstallDir
    if ($LASTEXITCODE -ne 0) { Fail "git clone 失败，请检查网络" }
}

# ---------- 安装依赖 ----------
Info "同步 Python 依赖 (uv sync) ..."
Push-Location $InstallDir
try {
    uv sync
    if ($LASTEXITCODE -ne 0) { Fail "uv sync 失败" }

    Info "安装桌面端依赖 (npm install) ..."
    npm install
    if ($LASTEXITCODE -ne 0) { Fail "npm install 失败" }

    Info "安装前端依赖 (npm install --prefix ui) ..."
    npm install --prefix ui
    if ($LASTEXITCODE -ne 0) { Fail "npm install --prefix ui 失败" }
} finally {
    Pop-Location
}

# ---------- 嵌入模型（遵循应用逻辑：数据盘未配置时跳过，首启后自动下载）----------
Info "检查嵌入模型 (embedding model) ..."
Push-Location $InstallDir
@'
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
'@ | uv run python -
if ($LASTEXITCODE -ne 0) {
    Warn "嵌入模型检查失败（不影响安装，稍后可在应用内 配置中心 → 部署 页安装）"
}
Pop-Location

# ---------- Docker Desktop（失败仅警告，可稍后在应用内「部署」页重试）----------
if (Get-Command docker -ErrorAction SilentlyContinue) {
    Info "已检测到 Docker: $(docker --version)"
} else {
    $dockerInstalled = $false
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Info "安装 Docker Desktop（体积较大，可能需要数分钟）..."
        $dockerInstalled = Install-ByWinget "Docker.DockerDesktop"
        Update-SessionPath
    }
    if ($dockerInstalled -and (Get-Command docker -ErrorAction SilentlyContinue)) {
        # 尝试启动 Docker Desktop 完成首次初始化（接受协议、启用 WSL2 后端）
        $dockerDesktop = "C:\Program Files\Docker\Docker\Docker Desktop.exe"
        if (Test-Path $dockerDesktop) {
            Start-Process $dockerDesktop
            Ok "Docker Desktop 安装完成（已启动，请在弹出的窗口中完成首次设置）"
        } else {
            Ok "Docker Desktop 安装完成（请手动启动一次以完成初始化）"
        }
    } else {
        Warn "Docker 安装失败——不影响 PurrCat 本体安装，但沙盒 Bash 工具依赖它。"
        Warn "可稍后在应用内 配置中心 → 部署 页重试，或手动安装: https://docs.docker.com/desktop/install/windows-install/"
    }
}

# ---------- 生成 purrcat 命令 ----------
New-Item -ItemType Directory -Force -Path $BinDir | Out-Null
@'
@echo off
rem PurrCat CLI launcher
if "%PURRCAT_HOME%"=="" set "PURRCAT_HOME=%USERPROFILE%\purrcat"
cd /d "%PURRCAT_HOME%" || (
  echo [x] PurrCat source not found: %PURRCAT_HOME%
  exit /b 1
)
uv run python -m scripts.cli.main %*
'@ | Set-Content -Path "$BinDir\purrcat.cmd" -Encoding ascii

# ---------- 确保 ~/.local/bin 在用户 PATH ----------
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($userPath -notlike "*$BinDir*") {
    [Environment]::SetEnvironmentVariable("Path", "$userPath;$BinDir", "User")
    Info "已将 $BinDir 加入用户 PATH"
}

# ---------- 完成 ----------
Write-Host ""
Ok "PurrCat 安装完成!"
Write-Host ""
Write-Host "  源码位置:  $InstallDir"
Write-Host "  命令位置:  $BinDir\purrcat.cmd"
Write-Host ""
Write-Host "下一步:"
Write-Host "  1. 重新打开终端（使 PATH 生效）"
Write-Host "  2. 启动桌面端:    purrcat desktop start"
Write-Host "  3. 日常更新源码:  purrcat desktop update"
Write-Host ""
Write-Host "（沙盒镜像会在后端启动时自动拉取；其余组件均可在应用内 配置中心 → 部署 页管理）"
