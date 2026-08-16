import io
import os
import re
import urllib.request
import zipfile
import traceback
import json
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

# 引入底层工具操作
from src.tool.callmcp.schema_manager import load_cached_schemas, refresh_schemas
from src.tool.search.mcp_search import MCPSearcher
from src.tool.search.skill_search import SkillSearcher
from src.tool.cron.cron_operations import list_crons, add_cron, delete_cron

# 🌟 新增：引入读取与保存 MCP 配置文件需要的依赖
from src.utils.config import get_mcp_config, MCP_CONFIG_PATH, SKILL_DIR, MCP_SOURCE_DIR, AGENT_CORE_DIR, GOAL_MD_PATH, HEARTBEAT_FILE

router = APIRouter(prefix="/api/tools", tags=["Tools Management"])


# ==========================================
# 1. MCP 服务器名称和工具名称 API
# ==========================================
@router.get("/mcp")
def get_mcp_tools_api():
    """获取内存/缓存里的 MCP 服务器及其包含的工具名称和描述"""
    try:
        schemas = load_cached_schemas()

        # 按照 server 名称进行分组组织
        result = {}
        for s in schemas:
            srv = s.get("server", "unknown")
            func = s.get("function", {})

            if srv not in result:
                result[srv] = []

            result[srv].append(
                {
                    "name": func.get("name", ""),
                    "description": func.get("description", ""),
                }
            )

        return result
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"获取 MCP 列表失败: {str(e)}")


# ==========================================
# 2. Skill 名称和技能描述 API
# ==========================================
@router.get("/skills")
def get_skills_api():
    """获取内存里的 Skill 名称和描述"""
    try:
        searcher = SkillSearcher()
        # searcher.skills 是一个列表，格式如 [{"name": "...", "description": "...", "dir_name": "..."}]
        return searcher.skills
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"获取 Skill 列表失败: {str(e)}")


# ==========================================
# Skill 在线安装 API
# ==========================================
class InstallSkillReq(BaseModel):
    url: str


@router.post("/skills/install")
def install_skill_api(req: InstallSkillReq):
    """根据 GitHub URL 下载第三方 Skill 并热更新内存"""
    try:
        url = req.url
        # 1. 解析 GitHub URL (支持子目录或仓库根目录两种形式)
        match = re.match(r"https?://github\.com/([^/]+)/([^/]+)/tree/([^/]+)(?:/(.*))?", url)
        if not match:
            raise HTTPException(
                status_code=400,
                detail="URL格式错误！正确格式示例: https://github.com/owner/repo/tree/branch/path/to/skill",
            )

        owner, repo, branch, path = match.groups()
        path = (path or "").strip("/")
        # 仓库根目录即 skill 时，用仓库名作为 skill 名
        skill_name = os.path.basename(path) if path else repo

        # 2. 定位 skills 文件夹
        dest_dir = os.path.join(SKILL_DIR, skill_name)
        zip_url = f"https://github.com/{owner}/{repo}/archive/refs/heads/{branch}.zip"

        # 3. 内存下载并仅解压目标子文件夹
        response = urllib.request.urlopen(zip_url)
        zip_data = response.read()

        with zipfile.ZipFile(io.BytesIO(zip_data)) as z:
            root_folder = z.namelist()[0].split("/")[0]
            target_prefix = f"{root_folder}/{path}".rstrip("/") + "/"

            extracted_count = 0
            for file_info in z.infolist():
                if file_info.filename.startswith(target_prefix):
                    relative_path = file_info.filename[len(target_prefix) :]
                    if not relative_path:
                        continue

                    local_path = os.path.join(dest_dir, relative_path)
                    if file_info.is_dir():
                        os.makedirs(local_path, exist_ok=True)
                    else:
                        os.makedirs(os.path.dirname(local_path), exist_ok=True)
                        with open(local_path, "wb") as f:
                            f.write(z.read(file_info.filename))
                    extracted_count += 1

            if extracted_count == 0:
                raise HTTPException(
                    status_code=404, detail=f"仓库中找不到文件夹 '{path}'"
                )

        # 4. 解压成功后，触发 searcher 的内存热更新
        searcher = SkillSearcher()
        searcher.reload_index()

        return {
            "status": "success",
            "message": f"Skill '{skill_name}' 下载成功并已热加载入内存！",
        }

    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Skill 下载/解压失败: {str(e)}")


# ==========================================
# 3. Cron 闹钟列表 API
# ==========================================
@router.get("/cron")
def get_crons_api():
    """读取 cron.json 返回现有闹钟列表"""
    try:
        return list_crons()
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"获取闹钟列表失败: {str(e)}")


# ==========================================
# 4. MCP Schema 刷新 API
# ==========================================
@router.post("/mcp/refresh")
def refresh_mcp_api():
    """手动刷新 MCP Schema 并更新内存检索树"""
    try:
        # 1. 重新拉取物理文件
        schemas = refresh_schemas()
        # 2. 触发 Searcher 的内存热更新
        MCPSearcher().reload_index()

        return {
            "status": "success",
            "message": f"MCP 缓存已刷新，共加载 {len(schemas)} 个工具",
        }
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"刷新 MCP 失败: {str(e)}")


# ==========================================
# 🌟 新增：MCP 录入安装 API
# ==========================================
class InstallMCPReq(BaseModel):
    config_json: str
    repo: str = ""  # 源码仓库地址；官方仓库（PurrPod/mcps）时额外下载源码


def _download_official_mcp_source(repo: str, server_names: list) -> str:
    """官方 MCP：从 PurrPod/mcps 仓库下载对应子文件夹源码到 ~/.purrcat/mcps/"""
    match = re.match(r"https?://github\.com/PurrPod/mcps", repo)
    if not match:
        return ""

    zip_url = "https://github.com/PurrPod/mcps/archive/refs/heads/main.zip"
    response = urllib.request.urlopen(zip_url)
    zip_data = response.read()

    downloaded = []
    with zipfile.ZipFile(io.BytesIO(zip_data)) as z:
        root_folder = z.namelist()[0].split("/")[0]

        for name in server_names:
            # 兼容仓库内不同目录层级：<root>/<name>/ 或 <root>/mcps/<name>/
            target_prefix = None
            for candidate in (f"{root_folder}/{name}/", f"{root_folder}/mcps/{name}/"):
                if any(f.filename.startswith(candidate) for f in z.infolist()):
                    target_prefix = candidate
                    break
            if not target_prefix:
                continue

            dest_dir = os.path.join(MCP_SOURCE_DIR, name)
            for file_info in z.infolist():
                if file_info.filename.startswith(target_prefix):
                    relative_path = file_info.filename[len(target_prefix):]
                    if not relative_path:
                        continue
                    local_path = os.path.join(dest_dir, relative_path)
                    if file_info.is_dir():
                        os.makedirs(local_path, exist_ok=True)
                    else:
                        os.makedirs(os.path.dirname(local_path), exist_ok=True)
                        with open(local_path, "wb") as f:
                            f.write(z.read(file_info.filename))
            downloaded.append(name)

    return ",".join(downloaded)


@router.post("/mcp/install")
def install_mcp_api(req: InstallMCPReq):
    """解析并合并用户传入的 MCP Server JSON 配置，落盘并热更新；官方 MCP 额外下载源码"""
    try:
        new_config = json.loads(req.config_json)
        if "mcpServers" not in new_config:
            raise HTTPException(
                status_code=400, detail="JSON 格式必须以 'mcpServers' 为顶层键"
            )

        # 1. 读出现有配置
        existing_config = get_mcp_config()
        if "mcpServers" not in existing_config:
            existing_config["mcpServers"] = {}

        # 2. 遍历并合并配置
        for srv_name, srv_conf in new_config["mcpServers"].items():
            existing_config["mcpServers"][srv_name] = srv_conf

        # 3. 落盘保存配置文件 mcp_config.json
        os.makedirs(os.path.dirname(MCP_CONFIG_PATH), exist_ok=True)
        with open(MCP_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(existing_config, f, indent=2, ensure_ascii=False)

        # 4. 官方 MCP：下载源码到 ~/.purrcat/mcps/（失败不阻断配置安装）
        source_note = ""
        try:
            downloaded = _download_official_mcp_source(
                req.repo, list(new_config["mcpServers"].keys())
            )
            if downloaded:
                source_note = f"；已下载官方源码: {downloaded}"
        except Exception as e:
            traceback.print_exc()
            source_note = f"；官方源码下载失败: {e}"

        # 5. 刷新 Schema 并重建检索树 (它会自动通信子进程并更新 mcp_schema.json)
        schemas = refresh_schemas()
        MCPSearcher().reload_index()

        return {
            "status": "success",
            "message": f"MCP 配置已合并并热加载成功！当前系统共载入 {len(schemas)} 个工具。{source_note}",
        }

    except json.JSONDecodeError:
        raise HTTPException(
            status_code=400, detail="输入的不是合法的 JSON 格式，请检查语法"
        )
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"安装 MCP 失败: {str(e)}")


# ==========================================
# 🌟 MCP 已配置列表 API（市场"已安装"检测用）
# ==========================================
@router.get("/mcp/list")
def list_configured_mcps_api():
    """返回 mcp_config.json 中已配置的 MCP Server 名称列表"""
    try:
        config = get_mcp_config()
        return list(config.get("mcpServers", {}).keys())
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"获取 MCP 配置列表失败: {str(e)}")


# ==========================================
# 5. Skill 刷新 API
# ==========================================
@router.post("/skills/refresh")
def refresh_skills_api():
    """手动扫描本地 Skill 文件夹并更新内存检索树"""
    try:
        searcher = SkillSearcher()
        searcher.reload_index()

        return {
            "status": "success",
            "message": f"Skill 已刷新，共加载 {len(searcher.skills)} 个技能",
        }
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"刷新 Skill 失败: {str(e)}")


# ==========================================
# 6. 添加、删除闹钟 API
# ==========================================
class AddCronReq(BaseModel):
    title: str
    trigger_time: str
    repeat_rule: str = "none"
    task_hook: str = "Agent"
    task_inputs: dict = {}


@router.post("/cron")
def add_cron_api(req: AddCronReq):
    """添加闹钟"""
    try:
        result = add_cron(
            title=req.title,
            trigger_time=req.trigger_time,
            repeat_rule=req.repeat_rule,
            task_hook=req.task_hook,  # 🌟 透传参数
            task_inputs=req.task_inputs,  # 🌟 透传参数
        )
        return {"status": "success", "data": result}
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=400, detail=f"添加闹钟失败: {str(e)}")


@router.delete("/cron/{identifier}")
def delete_cron_api(identifier: str):
    """删除闹钟 (支持传 id 或 title)"""
    try:
        result = delete_cron(identifier)
        return {"status": "success", "data": result}
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=400, detail=f"删除闹钟失败: {str(e)}")


# ==========================================
# 7. Agent 心跳 API（GOAL.md 定时注入）
# ==========================================


class HeartbeatReq(BaseModel):
    interval: int  # 秒，最短 60
    active: bool
    goal: str = ""  # GOAL.md 内容；开启心跳时必填非空


@router.get("/heartbeat")
def get_heartbeat_api():
    """获取心跳配置 + GOAL.md 当前内容"""
    from src.agent.heartbeat import get_heartbeat_manager

    cfg = get_heartbeat_manager().get_config()
    return {"interval": cfg["interval"], "active": cfg["active"], "goal": get_heartbeat_manager().read_goal()}


@router.post("/heartbeat")
def save_heartbeat_api(req: HeartbeatReq):
    """保存心跳配置；开启心跳时必须提交非空 GOAL.md 内容"""
    from src.agent.heartbeat import get_heartbeat_manager, MIN_INTERVAL

    goal = (req.goal or "").strip()
    if req.active and not goal:
        raise HTTPException(status_code=400, detail="GOAL.md 内容为空，无法开启心跳")

    try:
        os.makedirs(AGENT_CORE_DIR, exist_ok=True)

        # 先落盘 GOAL.md
        with open(GOAL_MD_PATH, "w", encoding="utf-8") as f:
            f.write(req.goal or "")

        # 再落盘心跳配置（原子写入）
        cfg = {"interval": max(MIN_INTERVAL, req.interval), "active": req.active}
        tmp_file = HEARTBEAT_FILE + ".tmp"
        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
        os.replace(tmp_file, HEARTBEAT_FILE)
        return {"status": "success", "data": cfg}
    except HTTPException:
        raise
    except Exception as e:
        import traceback

        traceback.print_exc()
        raise HTTPException(status_code=400, detail=f"保存心跳配置失败: {str(e)}")
