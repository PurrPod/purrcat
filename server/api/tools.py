import traceback
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

# 引入底层工具操作
from src.tool.callmcp.schema_manager import load_cached_schemas, refresh_schemas
from src.tool.search.mcp_search import MCPSearcher
from src.tool.search.skill_search import SkillSearcher
from src.tool.cron.cron_operations import list_crons, add_cron, delete_cron

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
                
            result[srv].append({
                "name": func.get("name", ""),
                "description": func.get("description", "")
            })
            
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
            "message": f"MCP 缓存已刷新，共加载 {len(schemas)} 个工具"
        }
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"刷新 MCP 失败: {str(e)}")


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
            "message": f"Skill 已刷新，共加载 {len(searcher.skills)} 个技能"
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

@router.post("/cron")
def add_cron_api(req: AddCronReq):
    """添加闹钟"""
    try:
        result = add_cron(
            title=req.title, 
            trigger_time=req.trigger_time, 
            repeat_rule=req.repeat_rule
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