"""桌面应用扫描器 - 跨平台扫描本地已安装的桌面软件

Windows 扫描来源:
1. 注册表卸载项 (传统 Win32 桌面程序)
2. 开始菜单 + 桌面快捷方式 (.lnk)
3. UWP / Microsoft Store 应用

macOS 扫描来源:
1. /Applications 目录下的 .app 应用包
2. ~/Applications 目录下的 .app 应用包
3. System Applications (Spotlight/mdfind 搜索)

Linux 扫描来源:
1. /usr/share/applications 下的 .desktop 文件
2. ~/.local/share/applications 下的 .desktop 文件

输出: apps_inventory.json (应用清单)
"""

import os
import re
import json
import platform
import subprocess
import plistlib
from typing import List, Dict, Optional

from src.utils.config import PURRCAT_DIR, APP_CONFIG_PATH


def _scan_registry_uninstall() -> List[Dict]:
    """扫描注册表卸载项，获取传统 Win32 桌面程序"""
    apps = []
    try:
        import winreg

        roots = [
            (
                winreg.HKEY_LOCAL_MACHINE,
                r"Software\Microsoft\Windows\CurrentVersion\Uninstall",
            ),
            (
                winreg.HKEY_LOCAL_MACHINE,
                r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
            ),
            (
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Uninstall",
            ),
        ]

        for hive, subpath in roots:
            try:
                with winreg.OpenKey(hive, subpath) as key:
                    i = 0
                    while True:
                        try:
                            subkey_name = winreg.EnumKey(key, i)
                            with winreg.OpenKey(key, subkey_name) as subkey:
                                try:
                                    display_name, _ = winreg.QueryValueEx(
                                        subkey, "DisplayName"
                                    )
                                except FileNotFoundError:
                                    i += 1
                                    continue

                                if not display_name:
                                    i += 1
                                    continue

                                display_icon = None
                                install_location = None
                                try:
                                    display_icon, _ = winreg.QueryValueEx(
                                        subkey, "DisplayIcon"
                                    )
                                except FileNotFoundError:
                                    pass
                                try:
                                    install_location, _ = winreg.QueryValueEx(
                                        subkey, "InstallLocation"
                                    )
                                except FileNotFoundError:
                                    pass

                                path = None
                                if display_icon:
                                    match = re.match(
                                        r'^"?(.+?\.exe)"?,?\d*$', display_icon
                                    )
                                    if match:
                                        path = match.group(1)
                                    elif os.path.exists(display_icon):
                                        path = display_icon
                                elif install_location:
                                    path = install_location

                                if path and os.path.exists(path):
                                    apps.append(
                                        {
                                            "name": display_name,
                                            "path": path,
                                            "type": "win32",
                                        }
                                    )
                        except OSError:
                            break
                        i += 1
            except OSError:
                continue
    except ImportError:
        pass

    return apps


def _parse_lnk_target(lnk_path: str) -> Optional[str]:
    """解析 .lnk 快捷方式的目标路径"""
    try:
        # 方法1: 使用 win32com (需要 pywin32)
        from win32com.client import Dispatch

        shell = Dispatch("WScript.Shell")
        shortcut = shell.CreateShortcut(lnk_path)
        target = shortcut.TargetPath
        if target and os.path.exists(target) and target.lower().endswith(".exe"):
            return target
    except Exception:
        pass

    # 方法2: 使用正则解析 .lnk 二进制格式的字符串 (兜底)
    try:
        with open(lnk_path, "rb") as f:
            data = f.read()
        # 搜索 .exe 字符串 (UTF-16LE 编码)
        matches = re.findall(b"([\x20-\x7e]\x00){4,}", data)
        for match in matches:
            try:
                decoded = match.decode("utf-16-le", errors="ignore").rstrip("\x00")
                if decoded.lower().endswith(".exe") and os.path.exists(decoded):
                    return decoded
            except Exception:
                continue
    except Exception:
        pass

    return None


def _scan_shortcuts() -> List[Dict]:
    """扫描开始菜单和桌面的 .lnk 快捷方式"""
    apps = []

    lnk_dirs = [
        os.path.join(
            os.environ.get("ProgramData", ""),
            "Microsoft",
            "Windows",
            "Start Menu",
            "Programs",
        ),
        os.path.join(
            os.environ.get("AppData", ""),
            "Microsoft",
            "Windows",
            "Start Menu",
            "Programs",
        ),
        os.path.join(os.environ.get("USERPROFILE", ""), "Desktop"),
        os.path.join(os.environ.get("PUBLIC", ""), "Desktop"),
    ]

    for d in lnk_dirs:
        if not d or not os.path.isdir(d):
            continue
        try:
            for root, dirs, files in os.walk(d):
                for fname in files:
                    if not fname.lower().endswith(".lnk"):
                        continue
                    lnk_path = os.path.join(root, fname)
                    target = _parse_lnk_target(lnk_path)
                    if target:
                        app_name = os.path.splitext(fname)[0]
                        apps.append(
                            {
                                "name": app_name,
                                "path": target,
                                "type": "shortcut",
                            }
                        )
        except Exception:
            continue

    return apps


def _scan_uwp_apps() -> List[Dict]:
    """扫描 UWP / Microsoft Store 应用"""
    apps = []
    try:
        result = subprocess.run(
            [
                "powershell",
                "-Command",
                "Get-AppxPackage | Where-Object { $_.IsFramework -eq $false -and $_.SignatureKind -ne 'System' } | Select-Object Name, InstallLocation | ConvertTo-Json -Compress",
            ],
            capture_output=True,
            text=True,
            timeout=30,
            encoding="utf-8",
        )
        if result.returncode == 0 and result.stdout.strip():
            data = json.loads(result.stdout)
            if isinstance(data, dict):
                data = [data]
            for item in data:
                name = item.get("Name", "")
                location = item.get("InstallLocation", "")
                if name and location and os.path.isdir(location):
                    apps.append(
                        {
                            "name": name,
                            "path": location,
                            "type": "uwp",
                        }
                    )
    except Exception:
        pass

    return apps


def _scan_macos_apps() -> List[Dict]:
    """扫描 macOS 系统下的 .app 应用包"""
    apps = []
    scan_dirs = [
        "/Applications",
        os.path.expanduser("~/Applications"),
        "/System/Applications",
    ]

    def scan_app_dir(directory: str):
        if not os.path.isdir(directory):
            return
        try:
            for entry in os.listdir(directory):
                if not entry.endswith(".app"):
                    continue
                app_path = os.path.join(directory, entry)
                app_name = entry[:-4]  # 去掉 .app 后缀
                # 尝试从 Info.plist 读取可执行路径，获取更精确的启动路径
                exec_path = app_path
                info_plist = os.path.join(app_path, "Contents", "Info.plist")
                if os.path.exists(info_plist):
                    try:
                        with open(info_plist, "rb") as f:
                            plist = plistlib.load(f)
                        exe_name = plist.get("CFBundleExecutable")
                        if exe_name:
                            possible_exe = os.path.join(
                                app_path, "Contents", "MacOS", exe_name
                            )
                            if os.path.exists(possible_exe):
                                exec_path = possible_exe
                        display_name = plist.get("CFBundleDisplayName") or plist.get(
                            "CFBundleName"
                        )
                        if display_name:
                            app_name = display_name
                    except Exception:
                        pass
                apps.append(
                    {
                        "name": app_name,
                        "path": exec_path,
                        "type": "app",
                    }
                )
        except Exception:
            pass

    for d in scan_dirs:
        scan_app_dir(d)

    # 追加: 使用 mdfind (Spotlight) 搜索更多 .app
    try:
        result = subprocess.run(
            ["mdfind", "kMDItemContentType == 'com.apple.application-bundle'"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            seen_paths = {a["path"] for a in apps}
            for line in result.stdout.strip().split("\n"):
                line = line.strip()
                if not line or not line.endswith(".app"):
                    continue
                if line in seen_paths:
                    continue
                app_name = os.path.basename(line)[:-4]
                apps.append(
                    {
                        "name": app_name,
                        "path": line,
                        "type": "app",
                    }
                )
    except Exception:
        pass

    return apps


def _scan_linux_desktop_files() -> List[Dict]:
    """扫描 Linux 系统下的 .desktop 应用入口"""
    apps = []
    desktop_dirs = [
        "/usr/share/applications",
        "/usr/local/share/applications",
        os.path.expanduser("~/.local/share/applications"),
        "/var/lib/snapd/desktop/applications",
    ]

    def parse_desktop_file(filepath: str) -> Optional[Dict]:
        try:
            name = None
            exec_cmd = None
            no_display = False
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                in_section = False
                for line in f:
                    line = line.strip()
                    if line == "[Desktop Entry]":
                        in_section = True
                        continue
                    if line.startswith("[") and in_section:
                        break
                    if not in_section or "=" not in line:
                        continue
                    key, _, value = line.partition("=")
                    key = key.strip()
                    value = value.strip()
                    if key == "Name" and name is None:
                        name = value
                    elif key == "Exec" and exec_cmd is None:
                        # 去掉 %f %F %u %U 等参数占位符
                        exec_cmd = re.sub(r"\s%[a-zA-Z]", "", value).strip('"')
                    elif key == "NoDisplay" and value.lower() == "true":
                        no_display = True
            if no_display:
                return None
            if not name or not exec_cmd:
                return None
            # 只取第一个空格前的部分作为实际可执行路径
            exe_path = exec_cmd.split()[0].strip('"')
            return {
                "name": name,
                "path": exe_path if os.path.isabs(exe_path) else exec_cmd,
                "type": "desktop",
            }
        except Exception:
            return None

    for d in desktop_dirs:
        if not os.path.isdir(d):
            continue
        try:
            for fname in os.listdir(d):
                if not fname.endswith(".desktop"):
                    continue
                parsed = parse_desktop_file(os.path.join(d, fname))
                if parsed:
                    apps.append(parsed)
        except Exception:
            continue

    return apps


def scan_desktop_apps() -> List[Dict]:
    """扫描本地所有可用的桌面软件，返回去重后的应用列表（跨平台：Windows/macOS/Linux）"""
    system = platform.system()
    all_apps = []

    if system == "Windows":
        all_apps.extend(_scan_registry_uninstall())
        all_apps.extend(_scan_shortcuts())
        all_apps.extend(_scan_uwp_apps())
    elif system == "Darwin":  # macOS
        all_apps.extend(_scan_macos_apps())
    elif system == "Linux":
        all_apps.extend(_scan_linux_desktop_files())
    # 其他系统返回空列表，不崩溃

    # 去重 (基于 path)
    seen = set()
    unique_apps = []
    for app in all_apps:
        key = app["path"]
        if key not in seen:
            seen.add(key)
            unique_apps.append(app)

    # 按名称排序
    unique_apps.sort(key=lambda x: x["name"].lower())
    return unique_apps


def save_apps_inventory(apps: List[Dict], output_path: Optional[str] = None) -> str:
    """保存应用清单到 JSON 文件"""
    if output_path is None:
        PURRCAT_DIR.mkdir(parents=True, exist_ok=True)
        output_path = os.path.join(PURRCAT_DIR, "apps_inventory.json")

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(apps, f, indent=2, ensure_ascii=False)

    return output_path


def generate_app_config(apps: List[Dict]) -> Dict[str, str]:
    """从扫描结果生成 app_config.json 格式的映射 {应用名: 路径}"""
    config = {}
    for app in apps:
        name = app["name"]
        path = app["path"]
        if name and path:
            config[name] = path
    return config


def scan_and_save(generate_config: bool = False) -> Dict:
    """完整扫描流程：扫描 -> 保存清单 -> 可选生成白名单配置

    Args:
        generate_config: 是否生成 app_config.json 白名单配置（仅当文件不存在时才写入，避免覆盖用户手动配置）

    Returns:
        扫描结果摘要字典
    """
    apps = scan_desktop_apps()

    # 保存清单
    inventory_path = save_apps_inventory(apps)

    # 统计
    win32_count = sum(1 for a in apps if a["type"] == "win32")
    shortcut_count = sum(1 for a in apps if a["type"] == "shortcut")
    uwp_count = sum(1 for a in apps if a["type"] == "uwp")

    result = {
        "total": len(apps),
        "win32": win32_count,
        "shortcut": shortcut_count,
        "uwp": uwp_count,
        "inventory_path": inventory_path,
        "apps": apps,
    }

    # 可选：仅在 app_config.json 不存在时才自动生成，避免覆盖用户手动配置
    if generate_config and apps:
        if not os.path.exists(APP_CONFIG_PATH):
            config = generate_app_config(apps)
            from src.utils.config import _save_json_file

            _save_json_file(APP_CONFIG_PATH, config)
            result["app_config_path"] = APP_CONFIG_PATH
            result["config_generated"] = True
        else:
            result["config_skipped"] = True
            result["config_skip_reason"] = (
                "app_config.json 已存在，跳过自动生成以保护用户手动配置"
            )

    return result


if __name__ == "__main__":
    print("🔍 正在扫描本地桌面应用...")
    result = scan_and_save(generate_config=True)

    print("\n📊 扫描完成!")
    print(f"   总计: {result['total']} 个应用")
    print(
        f"   Win32: {result['win32']} | 快捷方式: {result['shortcut']} | UWP: {result['uwp']}"
    )
    print(f"   清单: {result['inventory_path']}")
    if result.get("config_generated"):
        print(f"   ✅ 白名单已生成: {result['app_config_path']}")
    elif result.get("config_skipped"):
        print(f"   ⚠️  白名单跳过: {result['config_skip_reason']}")
    print("\n🏆 应用列表 Top 20:")
    for app in result["apps"][:20]:
        print(f"   [{app['type']}] {app['name']} -> {app['path']}")
    if len(result["apps"]) > 20:
        print(f"   ... 还有 {len(result['apps']) - 20} 个应用")
