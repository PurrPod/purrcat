import json
import contextlib
import os
import sys
from pathlib import Path
from typing import Any, Dict

if sys.platform == "win32":
    import msvcrt
else:
    import fcntl

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC_DIR = os.path.join(BASE_DIR, "src")

PURRCAT_DIR = str(Path.home() / ".purrcat")
MODEL_CONFIG_PATH = os.path.join(PURRCAT_DIR, "model.json")
SENSOR_CONFIG_PATH = os.path.join(PURRCAT_DIR, "activate_sensor.json")
FILE_CONFIG_PATH = os.path.join(PURRCAT_DIR, "file.json")
MCP_CONFIG_PATH = os.path.join(PURRCAT_DIR, "mcp_config.json")


def _read_settings() -> Dict[str, Any]:
    """读取 settings.json；缺失、损坏或非对象结构一律返回空 dict。"""
    settings_path = os.path.join(PURRCAT_DIR, "settings.json")
    if not os.path.exists(settings_path):
        return {}
    try:
        with open(settings_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


# 大型数据目录：用户可选，默认 = ~/.purrcat
def _get_data_root() -> str:
    """从 settings.json 读用户配置的 data_root，默认返回 PURRCAT_DIR。
    只接受非空绝对路径，其它一律回退默认，防止填错搞坏路径。"""
    value = _read_settings().get("data_root")
    if isinstance(value, str) and value.strip() and os.path.isabs(value.strip()):
        return value.strip()
    return PURRCAT_DIR


def is_data_root_configured() -> bool:
    """settings.json 里是否已配置过 data_root（首启引导是否已完成的判定依据）。
    数据根目录支持随时变更：走配置中心的迁移入口（搬迁数据后重启生效）。"""
    return bool(_read_settings().get("data_root"))


DATA_ROOT = _get_data_root()

# 配置类数据（记忆/数据库等）绑定 ~/.purrcat
DATA_DIR = os.path.join(PURRCAT_DIR, "data")
MEMORY_DIR = os.path.join(DATA_DIR, "memory")
TRACKER_DIR = os.path.join(DATA_DIR, "tracker")
SCHEDULE_DIR = os.path.join(DATA_DIR, "schedule")
DATABASE_DIR = os.path.join(DATA_DIR, "database")

# 大型数据目录（agent_vm/embedding）走 DATA_ROOT，用户可选盘
AGENT_VM_DIR = os.path.join(DATA_ROOT, "agent_vm")
BUFFER_DIR = os.path.join(DATA_ROOT, "agent_vm", ".buffer")
MEMORY_PENDING_DIR = os.path.join(MEMORY_DIR, "buffer", "pending")
SKILL_DIR = os.path.join(PURRCAT_DIR, "skills")
GRAPHS_DIR = os.path.join(PURRCAT_DIR, "graph")
MCP_SOURCE_DIR = os.path.join(PURRCAT_DIR, "mcps")
SENSOR_EXTENSION_DIR = os.path.join(PURRCAT_DIR, "sensor")

SCHEDULE_FILE = os.path.join(SCHEDULE_DIR, "schedule.json")

AGENT_DIR = os.path.join(SRC_DIR, "agent")
AGENT_CORE_DIR = os.path.join(PURRCAT_DIR, "core")
SOUL_MD_PATH = os.path.join(AGENT_CORE_DIR, "SOUL.md")
CRON_FILE = os.path.join(AGENT_CORE_DIR, "cron.json")
HEARTBEAT_FILE = os.path.join(AGENT_CORE_DIR, "heartbeat.json")
GOAL_MD_PATH = os.path.join(AGENT_CORE_DIR, "GOAL.md")
SYSTEM_RULES_DIR = os.path.join(AGENT_DIR, "system_rules")

# 多个 Agent Loop（paradigm）YAML 配置目录；PARADIGM.yaml 为默认 Agent Loop
PARADIGMS_DIR = os.path.join(PURRCAT_DIR, "paradigms")

SESSIONS_DIR = os.path.join(DATA_DIR, "checkpoints", "agent")
SESSION_INDEX_PATH = os.path.join(SESSIONS_DIR, "index.json")

# 项目（会话分类器）：索引 + 每个项目一个文件夹（内含 MEMORY.md 项目记忆文件）
PROJECTS_DIR = os.path.join(DATA_DIR, "projects")
PROJECT_INDEX_PATH = os.path.join(PROJECTS_DIR, "index.json")

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(MEMORY_DIR, exist_ok=True)
os.makedirs(TRACKER_DIR, exist_ok=True)
os.makedirs(SCHEDULE_DIR, exist_ok=True)
os.makedirs(DATABASE_DIR, exist_ok=True)
os.makedirs(SESSIONS_DIR, exist_ok=True)
os.makedirs(PROJECTS_DIR, exist_ok=True)

MCP_SCHEMA_CACHE_FILE = os.path.join(PURRCAT_DIR, "mcp_schema.json")

# 🌟 ACP 网关本地鉴权 token（外部 sensor/编辑器经 HTTP 接入时校验）
ACP_TOKEN_FILE = os.path.join(PURRCAT_DIR, "acp_token")
# 🌟 ACP 转接脚本部署位置：~/.purrcat/bin/acp_relay.py
# 编辑器（Zed/Obsidian/VSCode）配置指向该稳定路径；启动时由 initial.py 从内置源
# 自动部署/刷新，App 升级后编辑器侧配置永不失效（relays 耐漂移：翻译全在网关）
ACP_BIN_DIR = os.path.join(PURRCAT_DIR, "bin")
ACP_RELAY_PATH = os.path.join(ACP_BIN_DIR, "acp_relay.py")


def get_acp_token() -> str:
    """读取 ACP 网关 token，首次调用时自动生成落盘"""
    tok = ""
    try:
        with open(ACP_TOKEN_FILE, "r", encoding="utf-8") as f:
            tok = f.read().strip()
    except OSError:
        pass
    if tok:
        return tok
    import secrets

    tok = secrets.token_hex(16)
    with open(ACP_TOKEN_FILE, "w", encoding="utf-8") as f:
        f.write(tok)
    return tok


GLOBAL_CONFIG_DIR = Path(PURRCAT_DIR)
GLOBAL_CONFIG_FILE = GLOBAL_CONFIG_DIR / "settings.json"


def _load_json_file(file_path: str) -> dict:
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[Config] 加载 JSON 文件失败 {file_path}: {e}")
        return {}


def _save_json_file(file_path: str, data: dict) -> bool:
    try:
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"[Config] 保存 JSON 文件失败 {file_path}: {e}")
        return False


def get_global_settings() -> dict:
    if not GLOBAL_CONFIG_FILE.exists():
        return {}
    try:
        with open(GLOBAL_CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


@contextlib.contextmanager
def _global_lock():
    """跨进程文件锁：settings.json 的读改写要整体互斥，避免旧实例/并发写回
    用过期快照整盘覆写、冲掉 data_root 等其它键。"""
    lock_path = str(GLOBAL_CONFIG_FILE) + ".lock"
    f = open(lock_path, "w")
    try:
        if sys.platform == "win32":
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_LOCK, 1)
        else:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        yield f
    finally:
        try:
            if sys.platform == "win32":
                f.seek(0)
                msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        except Exception:
            pass
        f.close()


def save_global_setting(key: str, value: Any) -> bool:
    GLOBAL_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with _global_lock():
        settings = get_global_settings()
        settings[key] = value
        ok = True
        try:
            with open(GLOBAL_CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(settings, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"[Config] 保存全局配置失败: {e}")
            ok = False
    return ok


def get_engine_preference() -> str:
    """容器引擎固定为 docker，无个性化配置"""
    return "docker"


def _read_json_if_exists(file_path: str) -> Dict[str, Any]:
    """配置文件存在才读取，缺失时返回空 dict（不打印错误）。"""
    if os.path.exists(file_path):
        return _load_json_file(file_path)
    return {}


def get_model_config() -> Dict[str, Any]:
    return _read_json_if_exists(MODEL_CONFIG_PATH)


def get_sensor_config() -> Dict[str, Any]:
    return _read_json_if_exists(SENSOR_CONFIG_PATH)


def get_file_config() -> Dict[str, Any]:
    return _read_json_if_exists(FILE_CONFIG_PATH)


def get_mcp_config() -> Dict[str, Any]:
    return _read_json_if_exists(MCP_CONFIG_PATH)


def get_agent_model() -> str:
    model_config = get_model_config()
    main = model_config.get("main", {})
    if isinstance(main, dict) and main:
        return next(iter(main.keys()))
    return "openai:deepseek-v4-flash"


def get_main_model_config(model_name: str | None = None) -> Dict[str, Any]:
    """取 model.json 中 main.<模型> 的配置。

    model_name 为空时取 main 下的第一个模型（与 get_agent_model 保持一致）。
    配置缺失或结构异常时返回空 dict。
    """
    main = get_model_config().get("main", {})
    if not isinstance(main, dict) or not main:
        return {}
    if model_name is None:
        model_name = next(iter(main.keys()), None)
    cfg = main.get(model_name, {}) if model_name else {}
    return cfg if isinstance(cfg, dict) else {}


def get_model_max_token(model_name: str | None = None, default: int = 500000) -> int:
    """上下文窗口上限；未配置时回落到默认值。"""
    value = get_main_model_config(model_name).get("max_token", default)
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def get_embedding_model() -> str:
    """嵌入模型固定存放在数据目录 DATA_ROOT/embedding，不再走 model.json 配置"""
    return os.path.join(DATA_ROOT, "embedding")


def get_data_dir() -> str:
    return DATA_DIR


def get_enriched_env() -> Dict[str, str]:
    """返回合并注册表最新 PATH 后的环境变量副本。

    Windows 上用户中途安装 uv/node 后，已运行进程的 PATH 不会自动更新
    （新开的 PowerShell 能 --version，但老进程里 shutil.which 仍找不到）。
    从 HKCU/HKLM 注册表把最新 PATH 合并进来，让 Sensor/MCP 子进程
    不重启也能找到新装的依赖。
    """
    env = os.environ.copy()
    if not sys.platform.startswith("win"):
        return env
    try:
        import winreg

        paths = []
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
            user_path, _ = winreg.QueryValueEx(k, "Path")
            paths.append(os.path.expandvars(user_path or ""))
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment",
        ) as k:
            sys_path, _ = winreg.QueryValueEx(k, "Path")
            paths.append(os.path.expandvars(sys_path or ""))

        merged = os.pathsep.join([env.get("PATH", "")] + paths)
        seen = set()
        parts = [
            p
            for p in merged.split(os.pathsep)
            if p and not (p.casefold() in seen or seen.add(p.casefold()))
        ]
        env["PATH"] = os.pathsep.join(parts)
    except Exception:
        pass
    return env


def get_container_engine(engine_preference: str = "docker") -> str:
    """统一只返回 docker 命令的绝对路径（引擎固定为 docker，无配置项）"""
    import shutil

    path = shutil.which("docker")
    if path:
        return path

    raise RuntimeError(
        "未检测到 docker 命令。请先安装 Docker Desktop：\n"
        "https://docs.docker.com/get-docker/"
    )
