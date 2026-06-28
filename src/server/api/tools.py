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
from src.utils.config import get_mcp_config, MCP_CONFIG_PATH

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
        # 1. 解析 GitHub URL (参考命令行工具的正则)
        match = re.match(r"https?://github\.com/([^/]+)/([^/]+)/tree/([^/]+)/(.*)", url)
        if not match:
            raise HTTPException(
                status_code=400,
                detail="URL格式错误！正确格式示例: https://github.com/owner/repo/tree/branch/path/to/skill",
            )

        owner, repo, branch, path = match.groups()
        skill_name = os.path.basename(path.rstrip("/"))

        # 2. 定位项目根目录的 skills 文件夹
        # server/api/tools.py 向上3层为项目根目录
        project_root = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
        dest_dir = os.path.join(project_root, "skills", skill_name)
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


@router.post("/mcp/install")
def install_mcp_api(req: InstallMCPReq):
    """解析并合并用户传入的 MCP Server JSON 配置，落盘并热更新"""
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

        # 4. 刷新 Schema 并重建检索树 (它会自动通信子进程并更新 mcp_schema.json)
        schemas = refresh_schemas()
        MCPSearcher().reload_index()

        return {
            "status": "success",
            "message": f"MCP 配置已合并并热加载成功！当前系统共载入 {len(schemas)} 个工具。",
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
# 7. 循环流水线任务 API
# ==========================================
LOOP_FILE = ".purrcat/core/loop.json"


class AddLoopReq(BaseModel):
    title: str
    interval: int
    task_hook: str = "Agent"
    task_inputs: dict = {}
    active: bool = True  # 🌟 新增：支持直接开启/关闭


@router.get("/loop")
def list_loops_api():
    """获取全量循环流水线任务清单"""
    LOOP_FILE = ".purrcat/core/loop.json"
    if not os.path.exists(LOOP_FILE):
        return []
    try:
        with open(LOOP_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"读取循环任务失败: {str(e)}")


@router.post("/loop")
def add_loop_api(req: AddLoopReq):
    """新增或修改循环定时流水线任务（含 Agent 专属心跳去重）"""
    LOOP_FILE = ".purrcat/core/loop.json"
    try:
        os.makedirs(os.path.dirname(LOOP_FILE), exist_ok=True)
        loops = []
        if os.path.exists(LOOP_FILE):
            with open(LOOP_FILE, "r", encoding="utf-8") as f:
                loops = json.load(f)

        # 🌟 核心去重：如果提交的是 Agent 心跳，先删掉历史所有的 Agent 记录
        if req.task_hook == "Agent":
            loops = [loop for loop in loops if loop.get("task_hook") != "Agent"]

        loop_id = "lp_" + __import__("uuid").uuid4().hex[:8]
        new_item = {
            "id": loop_id,
            "title": req.title,
            "interval": req.interval,
            "task_hook": req.task_hook,
            "task_inputs": req.task_inputs,
            "active": req.active,
        }
        loops.append(new_item)

        # 🌟 原子写入：先写临时文件，再 rename，防止写入冲突导致文件损坏
        tmp_file = LOOP_FILE + ".tmp"
        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump(loops, f, indent=2, ensure_ascii=False)
        os.replace(tmp_file, LOOP_FILE)
        return {"status": "success", "data": new_item}
    except Exception as e:
        import traceback

        traceback.print_exc()
        raise HTTPException(status_code=400, detail=f"保存循环任务失败: {str(e)}")


@router.delete("/loop/{loop_id}")
def delete_loop_api(loop_id: str):
    """根据 ID 精准剔除并注销指定的循环工作线程"""
    if not os.path.exists(LOOP_FILE):
        raise HTTPException(status_code=404, detail="循环配置文件不存在")
    try:
        with open(LOOP_FILE, "r", encoding="utf-8") as f:
            loops = json.load(f)

        filtered_loops = [loop for loop in loops if loop.get("id") != loop_id]
        if len(filtered_loops) == len(loops):
            raise HTTPException(status_code=404, detail="未找到该循环任务记录")

        # 🌟 原子写入：先写临时文件，再 rename，防止写入冲突导致文件损坏
        tmp_file = LOOP_FILE + ".tmp"
        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump(filtered_loops, f, indent=2, ensure_ascii=False)
        os.replace(tmp_file, LOOP_FILE)
        return {"status": "success", "message": f"工作线程 {loop_id} 已安全注销释放"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"注销循环任务异常: {str(e)}")
