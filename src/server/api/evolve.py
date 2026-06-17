import os
import re
import traceback
from typing import List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

# 引入现有的底层进化工厂方法
from evolve import (
    skill_improve_init,
    skill_generate_diff,
    skill_request_handle,
    skill_rollback,
    run_skill_eval_background
)

router = APIRouter(prefix="/api/evolve", tags=["Skill Evolution Factory"])

WORKPLACE_ROOT = "./agent_vm/skill_workplace"

# ==========================================
# 📌 Pydantic 校验模型
# ==========================================
class InitReq(BaseModel):
    skill_name: str
    is_upgrade: bool

class FileUpdateReq(BaseModel):
    content: str

class TestRunReq(BaseModel):
    workplace_id: str
    skill_name: str
    session_id: str = "main"

class HandleReq(BaseModel):
    workplace_id: str
    skill_name: str
    is_approved: bool
    reject_reason: Optional[str] = ""

class RollbackReq(BaseModel):
    skill_name: str


# ==========================================
# 🚀 1. 工厂大盘状态 API
# ==========================================
@router.get("/list")
def list_workplaces():
    """扫描 agent_vm/skill_workplace 返回正在加工的沙盒列表"""
    workplaces = []
    if os.path.exists(WORKPLACE_ROOT):
        for wid in os.listdir(WORKPLACE_ROOT):
            w_path = os.path.join(WORKPLACE_ROOT, wid)
            if os.path.isdir(w_path):
                # 寻找该沙盒内的 skill 文件夹名称（排除 iteration 缓存）
                skill_name = "unknown"
                for item in os.listdir(w_path):
                    if os.path.isdir(os.path.join(w_path, item)) and not item.startswith("iteration-"):
                        skill_name = item
                        break
                if skill_name != "unknown":
                    workplaces.append({
                        "workplace_id": wid, 
                        "skill_name": skill_name, 
                        "status": "processing"
                    })
    return workplaces

@router.post("/init")
def init_sandbox_api(req: InitReq):
    """初始化全新或升级用的沙盒"""
    try:
        msg = skill_improve_init(req.skill_name, req.is_upgrade)
        # 从底层返回的提示语中精准提取短 UUID 工作区 ID
        match = re.search(r"agent_vm/skill_workplace/([a-fA-F0-9]+)", msg)
        workplace_id = match.group(1) if match else "unknown"
        
        return {"status": "success", "workplace_id": workplace_id, "message": msg}
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"初始化沙盒失败: {str(e)}")


# ==========================================
# 📂 2. 沙盒文件读写 API
# ==========================================
@router.get("/file")
def get_file_api(workplace_id: str, skill_name: str, filename: str = ""):
    """读取沙盒内的文件，如果 filename 为空则返回附件列表"""
    base_path = os.path.join(WORKPLACE_ROOT, workplace_id, skill_name)
    
    if not os.path.exists(base_path):
        raise HTTPException(status_code=404, detail="沙盒工作区不存在")

    if not filename:
        attachments = []
        for root, _, files in os.walk(base_path):
            for file in files:
                # 过滤掉默认的核心文件，只暴露 scripts、assets 等作为附件
                if file not in ["SKILL.md", "evals.json", ".gitignore"]:
                    rel_path = os.path.relpath(os.path.join(root, file), base_path)
                    if not rel_path.startswith("evals"):
                        attachments.append(rel_path)
        return {"content": "", "attachments": attachments}

    file_path = os.path.join(base_path, filename)
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            return {"content": f.read()}
            
    raise HTTPException(status_code=404, detail="文件不存在")

@router.put("/file")
def update_file_api(workplace_id: str, skill_name: str, filename: str, req: FileUpdateReq):
    """前端保存 SKILL.md 或 evals.json 的修改"""
    try:
        file_path = os.path.join(WORKPLACE_ROOT, workplace_id, skill_name, filename)
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(req.content)
        return {"status": "success", "message": "保存成功"}
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"保存文件失败: {str(e)}")


# ==========================================
# 🧪 3. 测试与评测驱动 API
# ==========================================
@router.post("/test/run")
def run_evals_api(req: TestRunReq):
    """启动后台盲测"""
    try:
        run_skill_eval_background(req.workplace_id, req.skill_name, req.session_id)
        return {"status": "success", "message": "盲测已启动"}
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"启动测试失败: {str(e)}")

@router.get("/test/iterations")
def list_iterations_api(workplace_id: str):
    """获取目前已跑了几个 iteration 轮次"""
    w_path = os.path.join(WORKPLACE_ROOT, workplace_id)
    iters = []
    if os.path.exists(w_path):
        for item in os.listdir(w_path):
            match = re.match(r"iteration-(\d+)", item)
            if match:
                iters.append(int(match.group(1)))
    return sorted(iters)

@router.get("/test/report")
def get_eval_report_api(workplace_id: str, skill_name: str, iteration: Optional[int] = None):
    """获取指定轮次的测试报告 md"""
    w_path = os.path.join(WORKPLACE_ROOT, workplace_id)
    
    if iteration is None:
        iters = list_iterations_api(workplace_id)
        iteration = max(iters) if iters else None
        
    if iteration is not None:
        report_path = os.path.join(w_path, f"iteration-{iteration}", "eval_report.md")
        if os.path.exists(report_path):
            with open(report_path, "r", encoding="utf-8") as f:
                return {"report_md": f.read()}
                
    return {"report_md": ""}


# ==========================================
# 🤝 4. 审批与合并 API
# ==========================================
@router.get("/diff")
def get_diff_api(workplace_id: str, skill_name: str):
    """使用 Git 比对生成差异"""
    try:
        w_path = os.path.join(WORKPLACE_ROOT, workplace_id)
        diff_content = skill_generate_diff(skill_name, w_path)
        return {"diff_content": diff_content}
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"生成 Diff 失败: {str(e)}")

@router.post("/handle")
def handle_request_api(req: HandleReq):
    """
    处理合并请求。
    如果是 Reject（打回），则将理由写进 REJECT_REASON.md
    如果是 Approve，则真正执行合并。
    """
    try:
        w_path = os.path.join(WORKPLACE_ROOT, req.workplace_id)
        
        # 1. 人类拒绝合并，打回重做
        if not req.is_approved:
            reason_path = os.path.join(w_path, req.skill_name, "REJECT_REASON.md")
            with open(reason_path, "w", encoding="utf-8") as f:
                f.write(f"# Human Code Review Feedback\n\n你的 Pull Request 被人类拒绝。请阅读以下修复建议并重新修改代码：\n\n{req.reject_reason}")
            return {"status": "rejected", "message": "已将拒绝意见抛回沙盒，Agent可读取并继续调整。"}
            
        # 2. 人类同意合并
        msg = skill_request_handle(w_path, req.skill_name, req.is_approved)
        return {"status": "success", "message": msg}
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"处理合并请求失败: {str(e)}")

@router.post("/rollback")
def rollback_skill_api(req: RollbackReq):
    """强制撤销主库上一个 Git Commit"""
    try:
        msg = skill_rollback(req.skill_name)
        if "失败" in msg or "异常" in msg:
            raise HTTPException(status_code=400, detail=msg)
        return {"status": "success", "message": msg}
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"强制回滚失败: {str(e)}")