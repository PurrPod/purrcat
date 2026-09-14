# PurrCat one-line installer (source mode)
# Usage: irm https://raw.githubusercontent.com/PurrPod/purrcat/main/install.ps1 | iex
# Auto-installs missing prerequisites (git / uv / Node.js 18+ / Docker Desktop / embedding model)
# and registers a global `purrcat` command.
$ErrorActionPreference = "Stop"

$RepoUrl    = "https://github.com/PurrPod/purrcat.git"
$InstallDir = if ($env:PURRCAT_HOME) { $env:PURRCAT_HOME } else { "$env:USERPROFILE\purrcat" }
$BinDir     = "$env:USERPROFILE\.local\bin"

function Info($m) { Write-Host "[*] $m" -ForegroundColor Cyan }
function Ok($m)   { Write-Host "[+] $m" -ForegroundColor Green }
function Warn($m) { Write-Host "[!] $m" -ForegroundColor Yellow }
function Fail($m) { throw $m }

# Refresh session PATH after winget installs (registry is updated, current process is not)
function Update-SessionPath {
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
                [Environment]::GetEnvironmentVariable("Path", "User")
}

function Install-ByWinget($id) {
    Info "(Please allow the UAC prompt if it appears)"
    # Out-Host: pass winget output straight to the console so failures are visible
    winget install --id $id -e --accept-source-agreements --accept-package-agreements | Out-Host
    return ($LASTEXITCODE -eq 0)
}

# ---------- git ----------
if (Get-Command git -ErrorAction SilentlyContinue) {
    Info "git detected: $(git --version)"
} else {
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        Fail "winget not found; install git manually: https://git-scm.com/download/win"
    }
    Info "Installing git ..."
    $gitInstalled = Install-ByWinget "Git.Git"
    Update-SessionPath
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        if ($gitInstalled) {
            Fail "git was installed but is not in PATH yet; reopen your terminal and re-run this script"
        }
        Fail "git installation failed (see the winget output above); if it was the UAC prompt being dismissed, re-run and allow it. Otherwise install manually: https://git-scm.com/download/win"
    }
    Ok "git installed: $(git --version)"
}

# ---------- uv ----------
if (Get-Command uv -ErrorAction SilentlyContinue) {
    Info "uv detected: $(Get-Command uv).Source"
} else {
    Info "Installing uv ..."
    irm https://astral.sh/uv/install.ps1 | iex
}
$env:Path = "$BinDir;$env:Path"
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Fail "uv installation failed; run manually: irm https://astral.sh/uv/install.ps1 | iex"
}

# ---------- Node.js 18+ ----------
$nodeOk = $false
if (Get-Command node -ErrorAction SilentlyContinue) {
    $nodeMajor = [int]((node -v).TrimStart('v').Split('.')[0])
    if ($nodeMajor -ge 18) {
        Info "Node.js detected: $(node -v)"
        $nodeOk = $true
    } else {
        Warn "Node.js too old (found $(node -v), need 18+); upgrade first: https://nodejs.org/"
        Fail "Node.js version requirement not met"
    }
}
if (-not $nodeOk) {
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        Fail "winget not found; install Node.js 18+ manually: https://nodejs.org/"
    }
    Info "Installing Node.js LTS ..."
    $null = Install-ByWinget "OpenJS.NodeJS.LTS"
    Update-SessionPath
    if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
        Fail "Node.js installation failed; install an 18+ version manually: https://nodejs.org/"
    }
    Ok "Node.js installed: $(node -v)"
}

# ---------- Fetch source ----------
if (Test-Path "$InstallDir\.git") {
    Info "Existing source detected at $InstallDir, pulling latest ..."
    git -C $InstallDir pull --ff-only
    if ($LASTEXITCODE -ne 0) { Fail "git pull failed; check local changes and retry" }
} elseif (Test-Path $InstallDir) {
    Fail "Directory exists but is not a PurrCat repo: $InstallDir"
} else {
    Info "Cloning PurrCat source to $InstallDir ..."
    git clone --depth 1 $RepoUrl $InstallDir
    if ($LASTEXITCODE -ne 0) { Fail "git clone failed; check your network" }
}

# ---------- Dependencies ----------
Info "Syncing Python dependencies (uv sync) ..."
Push-Location $InstallDir
try {
    uv sync
    if ($LASTEXITCODE -ne 0) { Fail "uv sync failed" }

    Info "Installing desktop dependencies (npm install) ..."
    npm install
    if ($LASTEXITCODE -ne 0) { Fail "npm install failed" }

    Info "Installing frontend dependencies (npm install --prefix ui) ..."
    npm install --prefix ui
    if ($LASTEXITCODE -ne 0) { Fail "npm install --prefix ui failed" }
} finally {
    Pop-Location
}

# ---------- Embedding model (follows app logic: skip while data root unconfigured) ----------
Info "Checking embedding model ..."
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
    print("[+] Embedding model already present")
else:
    ensure_embedding_model()
    while _downloading_flag.is_set():
        time.sleep(1)
    if _model_exists(EMBEDDING_DIR):
        print("[+] Embedding model downloaded")
    else:
        print("[*] Embedding model not downloaded yet (auto-downloads after first-run data-root setup, or later from Config Center -> Deploy)")
'@ | uv run python -
if ($LASTEXITCODE -ne 0) {
    Warn "Embedding model check failed (non-fatal; retry later from the app's Config Center -> Deploy page)"
}
Pop-Location

# ---------- Docker Desktop (failure is non-fatal; retry later from the app's Deploy page) ----------
if (Get-Command docker -ErrorAction SilentlyContinue) {
    Info "Docker detected: $(docker --version)"
} else {
    $dockerInstalled = $false
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Info "Installing Docker Desktop (large download, may take several minutes) ..."
        $dockerInstalled = Install-ByWinget "Docker.DockerDesktop"
        Update-SessionPath
    }
    if ($dockerInstalled -and (Get-Command docker -ErrorAction SilentlyContinue)) {
        # Launch Docker Desktop to finish first-run setup (accept agreement, enable WSL2 backend)
        $dockerDesktop = "C:\Program Files\Docker\Docker\Docker Desktop.exe"
        if (Test-Path $dockerDesktop) {
            Start-Process $dockerDesktop
            Ok "Docker Desktop installed (launched; finish first-run setup in the window that opens)"
        } else {
            Ok "Docker Desktop installed (launch it once manually to finish initialization)"
        }
    } else {
        Warn "Docker installation failed — PurrCat itself is fine, but the sandboxed Bash tool requires it."
        Warn "Retry later from the app's Config Center -> Deploy page, or install manually: https://docs.docker.com/desktop/install/windows-install/"
    }
}

# ---------- Register purrcat command ----------
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

# ---------- Ensure ~/.local/bin is in user PATH ----------
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($userPath -notlike "*$BinDir*") {
    [Environment]::SetEnvironmentVariable("Path", "$userPath;$BinDir", "User")
    Info "Added $BinDir to user PATH"
}

# ---------- Done ----------
Write-Host ""
Ok "PurrCat installed successfully!"
Write-Host ""
Write-Host "  Source location:  $InstallDir"
Write-Host "  Command location: $BinDir\purrcat.cmd"
Write-Host ""
Write-Host "Next steps:"
Write-Host "  1. Reopen your terminal (to apply PATH)"
Write-Host "  2. Start the desktop app:   purrcat desktop start"
Write-Host "  3. Update source anytime:   purrcat desktop update"
Write-Host ""
Write-Host "(The sandbox image auto-pulls on backend start; all other components are managed in the app's Config Center -> Deploy page)"
