#!/usr/bin/env python3
"""
自动安装 Podman 环境的脚本

支持平台：
- Windows: 使用 winget 安装
- macOS: 使用 Homebrew 安装
- Linux: 使用系统包管理器安装
"""

import os
import platform
import subprocess
import sys


def _run_command(cmd, shell=True, capture_output=True, text=True):
    """运行命令并返回结果"""
    try:
        result = subprocess.run(
            cmd,
            shell=shell,
            capture_output=capture_output,
            text=text,
            timeout=180
        )
        return result.returncode == 0, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return False, "", "命令执行超时"
    except Exception as e:
        return False, "", str(e)


def install_podman_windows():
    """在 Windows 上使用 winget 安装 Podman"""
    print("🔍 检查 winget 是否可用...")
    
    success, stdout, stderr = _run_command("winget --version")
    if not success:
        print("❌ winget 不可用，请确保已安装 Windows App Installer")
        return False, "winget 不可用"
    
    print("🚀 使用 winget 安装 Podman...")
    success, stdout, stderr = _run_command(
        'winget install --id RedHat.Podman --accept-package-agreements --accept-source-agreements'
    )
    
    if success:
        print("✅ Podman 安装成功")
        return True, "Podman 安装成功"
    else:
        print(f"❌ Podman 安装失败: {stderr}")
        return False, f"安装失败: {stderr}"


def install_podman_macos():
    """在 macOS 上使用 Homebrew 安装 Podman"""
    print("🔍 检查 Homebrew 是否可用...")
    
    success, stdout, stderr = _run_command("brew --version")
    if not success:
        print("⚠️ Homebrew 不可用，尝试安装...")
        success, stdout, stderr = _run_command(
            '/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'
        )
        if not success:
            print("❌ Homebrew 安装失败")
            return False, "Homebrew 安装失败"
        print("✅ Homebrew 安装成功")
    
    print("🚀 使用 Homebrew 安装 Podman...")
    success, stdout, stderr = _run_command("brew install podman")
    
    if success:
        print("✅ Podman 安装成功")
        return True, "Podman 安装成功"
    else:
        print(f"❌ Podman 安装失败: {stderr}")
        return False, f"安装失败: {stderr}"


def install_podman_linux():
    """在 Linux 上安装 Podman"""
    distro = platform.linux_distribution()[0] if hasattr(platform, 'linux_distribution') else "unknown"
    
    if "debian" in distro.lower() or "ubuntu" in distro.lower():
        print("🚀 在 Debian/Ubuntu 上安装 Podman...")
        success, stdout, stderr = _run_command("sudo apt-get update && sudo apt-get install -y podman")
    elif "redhat" in distro.lower() or "centos" in distro.lower() or "fedora" in distro.lower():
        print("🚀 在 RHEL/CentOS/Fedora 上安装 Podman...")
        success, stdout, stderr = _run_command("sudo dnf install -y podman")
    elif "arch" in distro.lower():
        print("🚀 在 Arch Linux 上安装 Podman...")
        success, stdout, stderr = _run_command("sudo pacman -S --noconfirm podman")
    else:
        print(f"⚠️ 未知的 Linux 发行版: {distro}")
        print("🚀 尝试使用通用方法安装...")
        success, stdout, stderr = _run_command("which podman || (curl -fsSL https://get.podman.io | sh)")
    
    if success:
        print("✅ Podman 安装成功")
        return True, "Podman 安装成功"
    else:
        print(f"❌ Podman 安装失败: {stderr}")
        return False, f"安装失败: {stderr}"


def setup_podman_machine():
    """设置 Podman 虚拟机（主要针对 macOS 和 Windows）"""
    print("🚀 设置 Podman 虚拟机...")
    
    # 检查是否需要初始化
    success, stdout, stderr = _run_command("podman info", capture_output=True)
    if success and "machine" not in stdout.lower():
        print("✅ Podman 已配置完成")
        return True, "Podman 已配置完成"
    
    # 初始化 Podman 机器
    print("🔧 初始化 Podman 机器...")
    success, stdout, stderr = _run_command("podman machine init")
    if not success:
        print(f"⚠️ Podman 机器初始化警告: {stderr}")
    
    # 启动 Podman 机器
    print("🔧 启动 Podman 机器...")
    success, stdout, stderr = _run_command("podman machine start")
    if success:
        print("✅ Podman 虚拟机启动成功")
        return True, "Podman 虚拟机启动成功"
    else:
        print(f"❌ Podman 虚拟机启动失败: {stderr}")
        return False, f"虚拟机启动失败: {stderr}"


def setup():
    """主安装函数"""
    os_name = platform.system()
    print(f"🔍 检测到操作系统: {os_name}")
    
    try:
        if os_name == "Windows":
            success, message = install_podman_windows()
        elif os_name == "Darwin":
            success, message = install_podman_macos()
        elif os_name == "Linux":
            success, message = install_podman_linux()
        else:
            return False, f"不支持的操作系统: {os_name}"
        
        if success:
            return setup_podman_machine()
        
        return success, message
    
    except Exception as e:
        print(f"❌ 安装过程发生异常: {e}")
        return False, str(e)


if __name__ == "__main__":
    success, message = setup()
    print(f"\n{'✅' if success else '❌'} {message}")
    sys.exit(0 if success else 1)