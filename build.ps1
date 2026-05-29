<#
.SYNOPSIS
PurrCat AI 应用打包脚本

.DESCRIPTION
此脚本用于构建和打包 PurrCat AI 桌面应用，包括：
1. 后端 Python 依赖安装
2. 前端 React 应用构建
3. Tauri 桌面应用打包

.PARAMETER BuildType
构建类型：release 或 debug，默认 release

.PARAMETER SkipFrontend
跳过前端构建

.PARAMETER SkipBackend
跳过后端依赖安装

.PARAMETER SkipTauri
跳过 Tauri 打包

.EXAMPLE
.\build.ps1
执行完整的发布版本构建

.EXAMPLE
.\build.ps1 -BuildType debug
执行调试版本构建

.EXAMPLE
.\build.ps1 -SkipFrontend -SkipBackend
仅执行 Tauri 打包
#>

param(
    [string]$BuildType = "release",
    [switch]$SkipFrontend = $false,
    [switch]$SkipBackend = $false,
    [switch]$SkipTauri = $false
)

$ErrorActionPreference = "Stop"

function Write-ColorOutput {
    param(
        [string]$Message,
        [ConsoleColor]$Color = [ConsoleColor]::White
    )
    $originalColor = $Host.UI.RawUI.ForegroundColor
    $Host.UI.RawUI.ForegroundColor = $Color
    Write-Host $Message
    $Host.UI.RawUI.ForegroundColor = $originalColor
}

function Test-Command {
    param([string]$Command)
    $exists = $null -ne (Get-Command $Command -ErrorAction SilentlyContinue)
    return $exists
}

Write-ColorOutput "=====================================" [ConsoleColor]::Cyan
Write-ColorOutput "    PurrCat AI 应用打包脚本" [ConsoleColor]::Cyan
Write-ColorOutput "=====================================" [ConsoleColor]::Cyan
Write-Host ""

# 检查 Node.js
if (-not (Test-Command "node")) {
    Write-ColorOutput "❌ 未检测到 Node.js，请先安装 Node.js" [ConsoleColor]::Red
    exit 1
}
Write-ColorOutput "✅ Node.js 已安装" [ConsoleColor]::Green

# 检查 npm
if (-not (Test-Command "npm")) {
    Write-ColorOutput "❌ 未检测到 npm" [ConsoleColor]::Red
    exit 1
}
Write-ColorOutput "✅ npm 已安装" [ConsoleColor]::Green

# 检查 Python
if (-not (Test-Command "python")) {
    Write-ColorOutput "❌ 未检测到 Python，请先安装 Python" [ConsoleColor]::Red
    exit 1
}
Write-ColorOutput "✅ Python 已安装" [ConsoleColor]::Green

# 检查 Rust (用于 Tauri)
if (-not $SkipTauri) {
    if (-not (Test-Command "cargo")) {
        Write-ColorOutput "❌ 未检测到 Rust (cargo)，请先安装 Rust" [ConsoleColor]::Red
        Write-ColorOutput "   安装地址: https://www.rust-lang.org/tools/install" [ConsoleColor]::Yellow
        exit 1
    }
    Write-ColorOutput "✅ Rust (cargo) 已安装" [ConsoleColor]::Green
}

Write-Host ""
Write-ColorOutput "🚀 开始构建过程..." [ConsoleColor]::Cyan

# 后端依赖安装
if (-not $SkipBackend) {
    Write-Host ""
    Write-ColorOutput "[1/3] 安装后端 Python 依赖..." [ConsoleColor]::Yellow
    
    $backendDir = "."
    $requirementsFile = Join-Path $backendDir "requirements.txt"
    
    if (-not (Test-Path $requirementsFile)) {
        Write-ColorOutput "⚠️ 未找到 requirements.txt，跳过依赖安装" [ConsoleColor]::Yellow
    } else {
        Write-Host "安装依赖到虚拟环境..."
        try {
            python -m venv .venv
            & ".venv\Scripts\Activate.ps1"
            pip install -r requirements.txt
            Write-ColorOutput "✅ 后端依赖安装完成" [ConsoleColor]::Green
        } catch {
            Write-ColorOutput "❌ 后端依赖安装失败: $_" [ConsoleColor]::Red
            exit 1
        }
    }
}

# 前端构建
if (-not $SkipFrontend) {
    Write-Host ""
    Write-ColorOutput "[2/3] 构建前端 React 应用..." [ConsoleColor]::Yellow
    
    $frontendDir = Join-Path $PWD.Path "ui"
    
    if (-not (Test-Path $frontendDir)) {
        Write-ColorOutput "❌ 前端目录不存在: $frontendDir" [ConsoleColor]::Red
        exit 1
    }
    
    Push-Location $frontendDir
    
    try {
        Write-Host "安装前端依赖..."
        npm install
        
        Write-Host "构建前端应用..."
        if ($BuildType -eq "release") {
            npm run build
        } else {
            npm run build:dev
        }
        
        Write-ColorOutput "✅ 前端构建完成" [ConsoleColor]::Green
    } catch {
        Write-ColorOutput "❌ 前端构建失败: $_" [ConsoleColor]::Red
        exit 1
    } finally {
        Pop-Location
    }
}

# Tauri 打包
if (-not $SkipTauri) {
    Write-Host ""
    Write-ColorOutput "[3/3] 使用 Tauri 打包桌面应用..." [ConsoleColor]::Yellow
    
    $tauriDir = "."
    
    Push-Location $tauriDir
    
    try {
        Write-Host "安装 Tauri CLI..."
        npm install -g @tauri-apps/cli
        
        Write-Host "执行 Tauri 构建..."
        if ($BuildType -eq "release") {
            tauri build
        } else {
            tauri build --debug
        }
        
        Write-ColorOutput "✅ Tauri 打包完成" [ConsoleColor]::Green
        Write-ColorOutput "📦 输出文件位于: src-tauri\target\$BuildType\bundle" [ConsoleColor]::Cyan
    } catch {
        Write-ColorOutput "❌ Tauri 打包失败: $_" [ConsoleColor]::Red
        exit 1
    } finally {
        Pop-Location
    }
}

Write-Host ""
Write-ColorOutput "=====================================" [ConsoleColor]::Cyan
Write-ColorOutput "    构建过程完成！" [ConsoleColor]::Cyan
Write-ColorOutput "=====================================" [ConsoleColor]::Cyan