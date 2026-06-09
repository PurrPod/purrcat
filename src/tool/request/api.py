"""Request 工具 API 层 - 物理删除并自动化执行生效"""

import json
import os
import urllib.request
import zipfile
import io

from src.tool.request.request_operations import REQUESTS_FILE, REQUEST_LOCK
from src.utils.config import FILE_CONFIG_PATH

def get_pending_requests() -> list:
    """获取待处理请求"""
    if not os.path.exists(REQUESTS_FILE): return []
    with REQUEST_LOCK:
        try:
            with open(REQUESTS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError: return []
    pending_list = [req for req in data.values() if req.get("status") == "pending"]
    pending_list.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return pending_list

def _grant_file_permission(req_type: str, target: str):
    """自动将目标路径写入 file.json 对应的权限组，实现人类授权豁免"""
    with open(FILE_CONFIG_PATH, "r", encoding="utf-8") as f:
        config = json.load(f)
        
    if "permissions" not in config:
        config["permissions"] = {"blocked": [], "readonly": [], "writable": []}
    perms = config["permissions"]

    target_norm = target.replace("\\", "/")
        
    if req_type == "file_read":
        if target_norm in perms["blocked"]: perms["blocked"].remove(target_norm)
        if target_norm not in perms["readonly"] and target_norm not in perms["writable"]:
            perms["readonly"].append(target_norm)
            
    elif req_type == "file_write":
        if target_norm in perms["blocked"]: perms["blocked"].remove(target_norm)
        if target_norm in perms["readonly"]: perms["readonly"].remove(target_norm)
        if target_norm not in perms["writable"]:
            perms["writable"].append(target_norm)
            
    with open(FILE_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

def _install_skill_from_github(skill_name: str):
    """下载并安装特定 Skill"""
    url = "https://github.com/PurrPod/skillpod/archive/refs/heads/main.zip"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    response = urllib.request.urlopen(req)
    zip_data = response.read()

    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    dest_base = os.path.join(project_root, "skills")
    
    extracted = False
    with zipfile.ZipFile(io.BytesIO(zip_data)) as z:
        for file_info in z.infolist():
            parts = file_info.filename.split('/')
            if len(parts) >= 4 and parts[1] in ['official', 'community'] and parts[2] == skill_name:
                rel_path = file_info.filename.split(f"/{skill_name}/", 1)[1]
                if not rel_path: continue 
                local_path = os.path.join(dest_base, skill_name, rel_path)
                if file_info.is_dir(): os.makedirs(local_path, exist_ok=True)
                else:
                    os.makedirs(os.path.dirname(local_path), exist_ok=True)
                    with open(local_path, "wb") as f: f.write(z.read(file_info.filename))
                extracted = True

    if not extracted: raise Exception(f"仓库未找到技能 '{skill_name}'")
    from src.tool.search.skill_search import SkillSearcher
    SkillSearcher().reload_index()

def resolve_request(req_id: str, approved: bool, feedback: str = "", ignore: bool = False) -> dict:
    if not os.path.exists(REQUESTS_FILE): return {"status": "error", "message": "文件不存在"}

    with REQUEST_LOCK:
        with open(REQUESTS_FILE, "r", encoding="utf-8") as f: data = json.load(f)
        if req_id not in data: return {"status": "error", "message": "请求找不到"}

        req = data[req_id]
        req_type, target = req.get("type"), req.get("target")

        if approved and not ignore:
            try:
                if req_type == "skill_install": _install_skill_from_github(target)
                elif req_type in ["file_read", "file_write"]: _grant_file_permission(req_type, target)
            except Exception as e:
                approved = False
                feedback = f"老板已同意，但执行失败: {str(e)}。{feedback}"

        if not ignore:
            decision_text = "【同意并已生效】" if approved else "【被拒绝】"
            callback_msg = f"🔔 【系统通知】请求 (ID: {req_id}) | 目标: {target} | 结果: {decision_text}\n批注: {feedback}"
            if approved: 
                callback_msg += "\n系统已为你自动下发权限或安装插件，请直接继续执行被挂起的任务。"
            
            from src.agent import agent_force_push
            agent_force_push(callback_msg, type="system")

        del data[req_id]
        with open(REQUESTS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    return {"status": "success", "message": "处理完毕并移除"}

def get_resolved_requests() -> list:
    """已废弃，直接返回空列表防前端报错"""
    return []

def delete_request(req_id: str) -> bool:
    """手动删除记录 (防前端按钮报错)"""
    if not os.path.exists(REQUESTS_FILE): return False
    with REQUEST_LOCK:
        try:
            with open(REQUESTS_FILE, "r", encoding="utf-8") as f: data = json.load(f)
            if req_id in data:
                del data[req_id]
                with open(REQUESTS_FILE, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                return True
        except Exception: pass
    return False