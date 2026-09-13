# PurrCat 一键安装脚本（源码模式）
# 用法: irm https://raw.githubusercontent.com/PurrPod/purrcat/main/install.ps1 | iex
$ErrorActionPreference = "Stop"

$RepoUrl    = "https://github.com/PurrPod/purrcat.git"
$InstallDir = if ($env:PURRCAT_HOME) { $env:PURRCAT_HOME } else { "$env:USERPROFILE\purrcat" }
$BinDir     = "$env:USERPROFILE\.local\bin"

function Info($m) { Write-Host "[*] $m" -ForegroundColor Cyan }
function Ok($m)   { Write-Host "[+] $m" -ForegroundColor Green }
function Fail($m) { throw $m }

# ---- 1. 前置检查: git / Node 18+ ----
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Fail "未检测到 git，请先安装: winget install Git.Git"
}
if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    Fail "未检测到 Node.js（需 18+），请先安装: winget install OpenJS.NodeJS.LTS"
}
$nodeMajor = [int]((node -v).TrimStart('v').Split('.')[0])
if ($nodeMajor -lt 18) {
    Fail "Node.js 版本过低（当前 $(node -v)，需 18+），请升级: https://nodejs.org/"
}

# ---- 2. 安装 uv（若无）----
if (Get-Command uv -ErrorAction SilentlyContinue) {
    Info "已检测到 uv: $(Get-Command uv).Source"
} else {
    Info "安装 uv 包管理器..."
    irm https://astral.sh/uv/install.ps1 | iex
}
$env:Path = "$BinDir;$env:Path"
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Fail "uv 安装失败，请手动执行: irm https://astral.sh/uv/install.ps1 | iex"
}

# ---- 3. 获取源码 ----
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

# ---- 4. 安装依赖 ----
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

# ---- 5. 生成 purrcat 命令 ----
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

# ---- 6. 确保 ~/.local/bin 在用户 PATH ----
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($userPath -notlike "*$BinDir*") {
    [Environment]::SetEnvironmentVariable("Path", "$userPath;$BinDir", "User")
    Info "已将 $BinDir 加入用户 PATH"
}

# ---- 7. 完成 ----
Write-Host ""
Ok "PurrCat 安装完成!"
Write-Host ""
Write-Host "  源码位置:  $InstallDir"
Write-Host "  命令位置:  $BinDir\purrcat.cmd"
Write-Host ""
Write-Host "下一步:"
Write-Host "  1. 重新打开终端（使 PATH 生效）"
Write-Host "  2. 启动桌面端:    purrcat desktop start"
Write-Host "  3. 初始化沙盒:    purrcat setup    （沙盒 Bash 依赖 Docker）"
Write-Host "  4. 日常更新源码:  purrcat desktop update"
