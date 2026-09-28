import json
import os
import re
import stat
import shutil
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
    sensor_factory_init,
    sensor_request_handle,
    run_sensor_eval_background,
)
from src.utils.config import SKILL_DIR, AGENT_VM_DIR, SENSOR_EXTENSION_DIR

router = APIRouter(prefix="/api/evolve", tags=["Evolution Factory"])


def get_root(module_type: str) -> str:
    return os.path.join(AGENT_VM_DIR, f"{module_type}_workplace")


def body_root(module_type: str, workplace_id: str, name: str) -> str:
    """沙盒内「本体」所在目录。

    skill/mcp 的本体是 workplace 下的同名子目录；sensor 的本体是 workplace
    根目录下的单个 <name>.py（没有独立子目录），故直接返回工作区根。
    """
    if module_type == "sensor":
        return os.path.join(get_root(module_type), workplace_id)
    return os.path.join(get_root(module_type), workplace_id, name)


# ==========================================
# 📌 Pydantic 校验模型
# ==========================================
class InitReq(BaseModel):
    type: str = "skill"
    name: str
    is_upgrade: bool
    goal: str = ""  # 本次构建目标（写入 GOAL.md 并嵌入 GUIDE.md）


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
    if module_type == "sensor":
        # sensor 本体是单文件：正式库 <name>.py ↔ 沙盒 <name>.py
        source_dir = os.path.join(SENSOR_EXTENSION_DIR, f"{name}.py")
        target_dir = os.path.join(workplace_root, f"{name}.py")
        label = "Sensor"
    elif module_type == "mcp":
        source_dir = f"./mcps/{name}"
        target_dir = os.path.join(workplace_root, name)
        label = "MCP"
    else:
        source_dir = os.path.join(SKILL_DIR, name)
        target_dir = os.path.join(workplace_root, name)
        label = "Skill"

    if not os.path.exists(source_dir):
        return f"这是一个全新的 {label}：{name}，无历史版本（全部为新增）。"

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
    if module_type == "sensor":
        repo_root = SENSOR_EXTENSION_DIR
        target = f"{name}.py"
    else:
        repo_root = "./mcps" if module_type == "mcp" else SKILL_DIR
        target = name
    git_dir = os.path.join(repo_root, ".git")

    if not os.path.exists(git_dir):
        return "回滚失败：没有找到 Git 仓库，无法追溯历史。"

    try:
        log_check = subprocess.run(
            ["git", "log", "--oneline", "--", target],
            cwd=repo_root,
            capture_output=True,
            text=True,
        )
        if not log_check.stdout.strip():
            return f"回滚失败：未找到 '{name}' 的任何 Git 提交历史。"

        subprocess.run(
            ["git", "checkout", "HEAD~1", "--", target],
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
            if not os.path.isdir(w_path):
                continue

            if type == "sensor":
                # sensor 工厂：本体是工作区根目录下的单个 <name>.py（不是同名子目录）
                item_name = "unknown"
                for item in sorted(os.listdir(w_path)):
                    if item.endswith(".py") and os.path.isfile(
                        os.path.join(w_path, item)
                    ):
                        item_name = item[:-3]
                        break
                if item_name != "unknown":
                    workplaces.append(
                        {"workplace_id": wid, "name": item_name, "status": "processing"}
                    )
                continue

            item_name = "unknown"
            for item in os.listdir(w_path):
                item_path = os.path.join(w_path, item)
                if not os.path.isdir(item_path) or item.startswith(
                    ("iteration-", "trigger-")
                ):
                    continue
                # skill 工厂：技能本体是含 SKILL.md 的目录（跳过 blind-* 等评估产物目录）
                if type == "skill" and not os.path.exists(
                    os.path.join(item_path, "SKILL.md")
                ):
                    continue
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
            msg, workplace_id = (
                mcp_upgrade_init(req.name, req.goal)
                if req.is_upgrade
                else mcp_improve_init(req.name, req.goal)
            )
        elif req.type == "sensor":
            msg, workplace_id = sensor_factory_init(req.name, req.is_upgrade, req.goal)
        else:
            msg, workplace_id = skill_improve_init(req.name, req.is_upgrade, req.goal)

        if not workplace_id:
            raise HTTPException(status_code=400, detail=msg)
        return {"status": "success", "workplace_id": workplace_id, "message": msg}
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"初始化沙盒失败: {str(e)}")


@router.get("/file")
def get_file_api(workplace_id: str, name: str, type: str = "skill", filename: str = ""):
    base_path = body_root(type, workplace_id, name)
    if not os.path.exists(base_path):
        raise HTTPException(status_code=404, detail="沙盒工作区不存在")

    if not filename:
        files_list = []
        for r, dirs, files in os.walk(base_path):
            # 评估产物目录（iteration-* / trigger-*）与依赖目录不进文件树
            dirs[:] = [
                d
                for d in dirs
                if d not in ("__pycache__", ".venv", "node_modules")
                and not d.startswith(("iteration-", "trigger-"))
            ]
            for file in files:
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
        file_path = os.path.join(body_root(type, workplace_id, name), filename)
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
        elif req.type == "sensor":
            run_sensor_eval_background(req.workplace_id, req.name)
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
        iter_dir = os.path.join(w_path, f"iteration-{iteration}")
        report_md = ""
        if type == "mcp":
            report_path = os.path.join(iter_dir, "test_report.md")
            if os.path.exists(report_path):
                with open(report_path, "r", encoding="utf-8") as f:
                    report_md = f.read()
        elif type == "sensor":
            report_path = os.path.join(iter_dir, "protocol_report.md")
            if os.path.exists(report_path):
                with open(report_path, "r", encoding="utf-8") as f:
                    report_md = f.read()
        else:
            # 同一迭代目录内合并展示：Trigger 报告在前，盲测报告在后（缺失则跳过）
            parts = []
            for report_name in ("trigger_report.md", "eval_report.md"):
                report_path = os.path.join(iter_dir, report_name)
                if os.path.exists(report_path):
                    with open(report_path, "r", encoding="utf-8") as f:
                        parts.append(f.read())
            report_md = "\n\n---\n\n".join(parts)
        if report_md:
            return {"report_md": report_md}
    return {"report_md": ""}


@router.get("/test/benchmark")
def get_benchmark_api(
    workplace_id: str, type: str = "sensor", iteration: Optional[int] = None
):
    """读取某轮体检的结构化结论（benchmark.json），供前端展示逐条判据与未覆盖项"""
    w_path = os.path.join(get_root(type), workplace_id)
    if iteration is None:
        iters = list_iterations_api(workplace_id, type)
        iteration = max(iters) if iters else None
    if iteration is None:
        return {"benchmark": None}

    bench_path = os.path.join(w_path, f"iteration-{iteration}", "benchmark.json")
    if not os.path.exists(bench_path):
        return {"benchmark": None}
    try:
        with open(bench_path, "r", encoding="utf-8") as f:
            return {"benchmark": json.load(f)}
    except (json.JSONDecodeError, OSError):
        return {"benchmark": None}


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
            reason_path = os.path.join(
                body_root(req.type, req.workplace_id, req.name), "REJECT_REASON.md"
            )
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
        elif req.type == "sensor":
            msg = sensor_request_handle(w_path, req.name, req.is_approved)
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


@router.delete("/workplace/{workplace_id}")
def delete_workplace_api(workplace_id: str, type: str = "skill"):
    """前端手动彻底删除工厂沙盒"""
    try:
        w_path = os.path.join(get_root(type), workplace_id)
        if not os.path.exists(w_path):
            raise HTTPException(status_code=404, detail="沙盒不存在或已被删除")

        def on_rm_error(func, path, exc_info):
            try:
                os.chmod(path, stat.S_IWRITE)
                func(path)
            except Exception:
                pass

        shutil.rmtree(w_path, onerror=on_rm_error)
        return {"status": "success", "message": "沙盒已彻底清理"}

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"沙盒删除失败: {str(e)}")
