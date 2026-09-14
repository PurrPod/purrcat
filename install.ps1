# PurrCat one-line installer (source mode)
# Usage: irm https://raw.githubusercontent.com/PurrPod/purrcat/main/install.ps1 | iex
# Auto-installs missing prerequisites (git / uv / Node.js 18+ / Docker Desktop / embedding model)
# and registers a global `purrcat` command.
$ErrorActionPreference = "Stop"

# Decode native tool output (winget) as UTF-8; otherwise CJK Windows shows mojibake
try { [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new() } catch { }
try { $Host.UI.RawUI.WindowTitle = "PurrCat Installer" } catch { }

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

# Some installers write PATH asynchronously; poll until the command shows up
function Wait-CommandOnPath($name, $timeoutSec = 15) {
    for ($i = 0; $i -lt ($timeoutSec * 2); $i++) {
        if (Get-Command $name -ErrorAction SilentlyContinue) { return $true }
        Update-SessionPath
        Start-Sleep -Milliseconds 500
    }
    return $false
}

function Install-ByWinget($id) {
    Info "(Please allow the UAC prompt if it appears)"
    # --source winget: bypass the msstore source, which is frequently broken (0x80070057)
    # Out-Host: stream winget output to the console so failures are visible
    winget install --id $id -e --source winget --accept-source-agreements --accept-package-agreements | Out-Host
    return ($LASTEXITCODE -eq 0)
}

# Fallback: official Git installer when winget is unusable (broken sources, blocked CDN, etc.)
function Install-GitBySetup {
    $ProgressPreference = "SilentlyContinue"  # speed up Invoke-WebRequest
    $r = Invoke-RestMethod "https://api.github.com/repos/git-for-windows/git/releases/latest"
    $asset = $r.assets | Where-Object { $_.name -match '^Git-.*-64-bit\.exe$' } | Select-Object -First 1
    if (-not $asset) { return $false }
    $setup = "$env:TEMP\git-setup.exe"
    Info "Downloading Git installer: $($asset.name) ..."
    Invoke-WebRequest $asset.browser_download_url -OutFile $setup
    Info "Running the installer (please allow the UAC prompt if it appears) ..."
    $p = Start-Process $setup -ArgumentList '/VERYSILENT','/NORESTART','/NOCANCEL','/SP-' -Wait -PassThru
    return ($p.ExitCode -eq 0)
}

# Fallback: official Node.js LTS MSI when winget is unusable
function Install-NodeBySetup {
    $ProgressPreference = "SilentlyContinue"  # speed up Invoke-WebRequest
    $lts = Invoke-RestMethod "https://nodejs.org/dist/index.json" | Where-Object { $_.lts } | Select-Object -First 1
    if (-not $lts) { return $false }
    $msi = "$env:TEMP\node-setup.msi"
    Info "Downloading Node.js $($lts.version) LTS ..."
    Invoke-WebRequest "https://nodejs.org/dist/$($lts.version)/node-$($lts.version)-x64.msi" -OutFile $msi
    Info "Running the installer (please allow the UAC prompt if it appears) ..."
    $p = Start-Process msiexec.exe -ArgumentList '/i', $msi, '/qn', '/norestart' -Wait -PassThru
    return ($p.ExitCode -eq 0)
}

# Fallback: uv from GitHub releases when astral.sh is unreachable
function Install-UvByGitHub {
    $ProgressPreference = "SilentlyContinue"  # speed up Invoke-WebRequest
    $r = Invoke-RestMethod "https://api.github.com/repos/astral-sh/uv/releases/latest"
    $asset = $r.assets | Where-Object { $_.name -match '^uv-x86_64-pc-windows-msvc\.zip$' } | Select-Object -First 1
    if (-not $asset) { return $false }
    $tmp = "$env:TEMP\uv-download"
    $zip = "$tmp.zip"
    Info "Downloading uv $($r.tag_name) from GitHub releases ..."
    Invoke-WebRequest $asset.browser_download_url -OutFile $zip
    Expand-Archive $zip -DestinationPath $tmp -Force
    New-Item -ItemType Directory -Force -Path $BinDir | Out-Null
    Get-ChildItem $tmp -Recurse -Include uv.exe, uvx.exe | Move-Item -Destination $BinDir -Force
    return (Test-Path "$BinDir\uv.exe")
}

# ---------- git ----------
if (Get-Command git -ErrorAction SilentlyContinue) {
    Info "git detected: $(git --version)"
} else {
    $gitInstalled = $false
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Info "Installing git ..."
        $gitInstalled = Install-ByWinget "Git.Git"
    }
    if (-not $gitInstalled) {
        Warn "winget failed; falling back to the official Git installer ..."
        $gitInstalled = Install-GitBySetup
    }
    Update-SessionPath
    if (-not (Wait-CommandOnPath git)) {
        if ($gitInstalled) {
            Fail "git was installed but is not in PATH yet; reopen your terminal and re-run this script"
        }
        Fail "git installation failed; install it manually: https://git-scm.com/download/win"
    }
    Ok "git installed: $(git --version)"
}

# ---------- uv ----------
if (Get-Command uv -ErrorAction SilentlyContinue) {
    Info "uv detected: $(Get-Command uv).Source"
} else {
    Info "Installing uv ..."
    # Run the official installer in a child process: isolates its exit behavior,
    # and keeps our $ErrorActionPreference=Stop from altering its internal error handling
    try {
        $uvScript = "$env:TEMP\uv-install.ps1"
        Invoke-WebRequest https://astral.sh/uv/install.ps1 -OutFile $uvScript
        powershell -NoProfile -ExecutionPolicy Bypass -File $uvScript
        if ($LASTEXITCODE -ne 0) {
            Warn "official uv installer exited with code $LASTEXITCODE; falling back to GitHub releases ..."
        }
    } catch {
        Warn "official uv installer failed ($($_.Exception.Message)); falling back to GitHub releases ..."
    }
}
$env:Path = "$BinDir;$env:Path"
if (-not (Wait-CommandOnPath uv)) {
    $null = Install-UvByGitHub
}
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Fail "uv installation failed; install it manually: https://docs.astral.sh/uv/getting-started/installation/"
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
    $nodeInstalled = $false
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Info "Installing Node.js LTS ..."
        $nodeInstalled = Install-ByWinget "OpenJS.NodeJS.LTS"
    }
    if (-not $nodeInstalled) {
        Warn "winget failed; falling back to the official Node.js LTS installer ..."
        $nodeInstalled = Install-NodeBySetup
    }
    Update-SessionPath
    if (-not (Wait-CommandOnPath node)) {
        if ($nodeInstalled) {
            Fail "Node.js was installed but is not in PATH yet; reopen your terminal and re-run this script"
        }
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
# Write via the registry API: SetEnvironmentVariable would change REG_EXPAND_SZ to REG_SZ,
# breaking %USERPROFILE%-style entries and WindowsApps aliases
$envKey = [Microsoft.Win32.Registry]::CurrentUser.OpenSubKey("Environment", $true)
$userPath = $envKey.GetValue("Path", "", [Microsoft.Win32.RegistryValueOptions]::DoNotExpandEnvironmentNames)
if ("$userPath" -notlike "*$BinDir*") {
    try { $kind = $envKey.GetValueKind("Path") } catch { $kind = [Microsoft.Win32.RegistryValueKind]::ExpandString }
    $newPath = if ([string]::IsNullOrEmpty($userPath)) { $BinDir } else { "$userPath;$BinDir" }
    $envKey.SetValue("Path", $newPath, $kind)
    Info "Added $BinDir to user PATH"
}
$envKey.Close()

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
