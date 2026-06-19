import os
import re
import subprocess
import traceback
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from datetime import datetime

# 引入现有的底层进化工厂方法
from src.evolve import (
    skill_improve_init,
    skill_request_handle,
    run_skill_eval_background,
    mcp_improve_init,
    mcp_upgrade_init,
    mcp_request_handle,
    run_mcp_eval_background,
)

router = APIRouter(prefix="/api/evolve", tags=["Evolution Factory"])


def get_root(module_type: str) -> str:
    return f"./agent_vm/{module_type}_workplace"


# ==========================================
# 📌 Pydantic 校验模型
# ==========================================
class InitReq(BaseModel):
    type: str = "skill"
    name: str
    is_upgrade: bool


class FileUpdateReq(BaseModel):
    content: str


class TestRunReq(BaseModel):
    type: str = "skill"
    workplace_id: str
    name: str
    session_id: str = "main"


class HandleReq(BaseModel):
    type: str = "skill"
    workplace_id: str
    name: str
    is_approved: bool
    reject_reason: Optional[str] = ""


class RollbackReq(BaseModel):
    type: str = "skill"
    name: str


# ==========================================
# 🔧 通用 Git 操作辅助函数
# ==========================================
def unified_generate_diff(name: str, workplace_root: str, module_type: str) -> str:
    source_dir = f"./mcps/{name}" if module_type == "mcp" else f"./skills/{name}"
    target_dir = os.path.join(workplace_root, name)

    if not os.path.exists(source_dir):
        return f"这是一个全新的 {'MCP' if module_type == 'mcp' else 'Skill'}：{name}，无历史版本（全部为新增）。"

    try:
        result = subprocess.run(
            ["git", "diff", "--no-index", source_dir, target_dir],
            capture_output=True,
            text=True,
        )
        diff_output = result.stdout
        if not diff_output.strip():
            return "文件内容与主库相比没有任何改变。"
        return diff_output
    except Exception as e:
        return f"差异对比生成失败: {str(e)}"


def unified_rollback(name: str, module_type: str) -> str:
    repo_root = "./mcps" if module_type == "mcp" else "./skills"
    git_dir = os.path.join(repo_root, ".git")

    if not os.path.exists(git_dir):
        return "回滚失败：没有找到 Git 仓库，无法追溯历史。"

    try:
        log_check = subprocess.run(
            ["git", "log", "--oneline", "--", name],
            cwd=repo_root,
            capture_output=True,
            text=True,
        )
        if not log_check.stdout.strip():
            return f"回滚失败：未找到 '{name}' 的任何 Git 提交历史。"

        subprocess.run(
            ["git", "checkout", "HEAD~1", "--", name],
            cwd=repo_root,
            check=True,
            capture_output=True,
        )

        current_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        commit_msg = (
            f"rollback {module_type} {name} to previous state at {current_date}"
        )

        subprocess.run(["git", "commit", "-m", commit_msg], cwd=repo_root, check=True)
        return f"回滚成功！'{name}' 已恢复至上一个版本，并生成了 Rollback Commit。"

    except subprocess.CalledProcessError as e:
        stderr = e.stderr.decode("utf-8") if e.stderr else str(e)
        return f"回滚执行异常：{stderr}"


# ==========================================
# 🚀 API 路由
# ==========================================
@router.get("/list")
def list_workplaces(type: str = "skill"):
    """扫描指定加工厂的沙盒列表"""
    workplaces = []
    root = get_root(type)
    if os.path.exists(root):
        for wid in os.listdir(root):
            w_path = os.path.join(root, wid)
            if os.path.isdir(w_path):
                item_name = "unknown"
                for item in os.listdir(w_path):
                    if os.path.isdir(
                        os.path.join(w_path, item)
                    ) and not item.startswith("iteration-"):
                        item_name = item
                        break
                if item_name != "unknown":
                    workplaces.append(
                        {"workplace_id": wid, "name": item_name, "status": "processing"}
                    )
    return workplaces


@router.post("/init")
def init_sandbox_api(req: InitReq):
    try:
        if req.type == "mcp":
            msg = (
                mcp_upgrade_init(req.name)
                if req.is_upgrade
                else mcp_improve_init(req.name)
            )
        else:
            msg = skill_improve_init(req.name, req.is_upgrade)

        match = re.search(rf"agent_vm/{req.type}_workplace/([a-fA-F0-9]+)", msg)
        workplace_id = match.group(1) if match else "unknown"
        return {"status": "success", "workplace_id": workplace_id, "message": msg}
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"初始化沙盒失败: {str(e)}")


@router.get("/file")
def get_file_api(workplace_id: str, name: str, type: str = "skill", filename: str = ""):
    base_path = os.path.join(get_root(type), workplace_id, name)
    if not os.path.exists(base_path):
        raise HTTPException(status_code=404, detail="沙盒工作区不存在")

    if not filename:
        files_list = []
        for r, _, files in os.walk(base_path):
            for file in files:
                if "__pycache__" in r or ".venv" in r or "node_modules" in r:
                    continue
                if file.endswith((".pyc", ".png", ".jpg")):
                    continue
                rel_path = os.path.relpath(os.path.join(r, file), base_path)
                files_list.append(rel_path)
        return {"content": "", "attachments": sorted(files_list)}

    file_path = os.path.join(base_path, filename)
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            return {"content": f.read()}
    raise HTTPException(status_code=404, detail="文件不存在")


@router.put("/file")
def update_file_api(
    workplace_id: str, name: str, filename: str, req: FileUpdateReq, type: str = "skill"
):
    try:
        file_path = os.path.join(get_root(type), workplace_id, name, filename)
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(req.content)
        return {"status": "success", "message": "保存成功"}
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"保存文件失败: {str(e)}")


@router.post("/test/run")
def run_evals_api(req: TestRunReq):
    try:
        if req.type == "mcp":
            run_mcp_eval_background(req.workplace_id, req.name, req.session_id)
        else:
            run_skill_eval_background(req.workplace_id, req.name, req.session_id)
        return {"status": "success", "message": "盲测已启动"}
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"启动测试失败: {str(e)}")


@router.get("/test/iterations")
def list_iterations_api(workplace_id: str, type: str = "skill"):
    w_path = os.path.join(get_root(type), workplace_id)
    iters = []
    if os.path.exists(w_path):
        for item in os.listdir(w_path):
            match = re.match(r"iteration-(\d+)", item)
            if match:
                iters.append(int(match.group(1)))
    return sorted(iters)


@router.get("/test/report")
def get_eval_report_api(
    workplace_id: str, name: str, type: str = "skill", iteration: Optional[int] = None
):
    w_path = os.path.join(get_root(type), workplace_id)
    if iteration is None:
        iters = list_iterations_api(workplace_id, type)
        iteration = max(iters) if iters else None

    if iteration is not None:
        report_name = "test_report.md" if type == "mcp" else "eval_report.md"
        report_path = os.path.join(w_path, f"iteration-{iteration}", report_name)
        if os.path.exists(report_path):
            with open(report_path, "r", encoding="utf-8") as f:
                return {"report_md": f.read()}
    return {"report_md": ""}


@router.get("/diff")
def get_diff_api(workplace_id: str, name: str, type: str = "skill"):
    try:
        w_path = os.path.join(get_root(type), workplace_id)
        return {"diff_content": unified_generate_diff(name, w_path, type)}
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"生成 Diff 失败: {str(e)}")


@router.post("/handle")
def handle_request_api(req: HandleReq):
    try:
        w_path = os.path.join(get_root(req.type), req.workplace_id)
        if not req.is_approved:
            reason_path = os.path.join(w_path, req.name, "REJECT_REASON.md")
            with open(reason_path, "w", encoding="utf-8") as f:
                f.write(
                    f"# Human Code Review Feedback\n\n你的 Pull Request 被人类拒绝。请阅读以下修复建议并重新修改代码：\n\n{req.reject_reason}"
                )
            return {
                "status": "rejected",
                "message": "已将拒绝意见抛回沙盒，Agent可读取并继续调整。",
            }

        if req.type == "mcp":
            msg = mcp_request_handle(w_path, req.name, req.is_approved)
        else:
            msg = skill_request_handle(w_path, req.name, req.is_approved)
        return {"status": "success", "message": msg}
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"处理合并请求失败: {str(e)}")


@router.post("/rollback")
def rollback_skill_api(req: RollbackReq):
    try:
        msg = unified_rollback(req.name, req.type)
        if "失败" in msg or "异常" in msg:
            raise HTTPException(status_code=400, detail=msg)
        return {"status": "success", "message": msg}
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"强制回滚失败: {str(e)}")
