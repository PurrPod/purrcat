"""进化工厂服务层：沙盒扫描、文件读写、评测启动/报告读取与 Git 回滚。

路由层（evolve.py）只保留 Pydantic 模型与薄委托；本模块保留原有
HTTPException 语义与返回结构。
"""

from __future__ import annotations

import json
import os
import re
import shutil
import stat
import subprocess
import traceback
from datetime import datetime
from typing import Optional

import yaml
from fastapi import HTTPException

from src.evolve import (
    agentloop_factory_init,
    agentloop_request_handle,
    graph_factory_init,
    graph_request_handle,
    mcp_improve_init,
    mcp_request_handle,
    mcp_upgrade_init,
    record_trace_meta,
    run_mcp_eval_background,
    run_sensor_eval_background,
    run_skill_eval_background,
    sensor_factory_init,
    sensor_request_handle,
    skill_improve_init,
    skill_request_handle,
)
from src.utils.config import (
    AGENT_VM_DIR,
    GRAPHS_DIR,
    PARADIGMS_DIR,
    SENSOR_EXTENSION_DIR,
    SKILL_DIR,
)


def get_root(module_type: str) -> str:
    return os.path.join(AGENT_VM_DIR, f"{module_type}_workplace")


def body_root(module_type: str, workplace_id: str, name: str) -> str:
    """沙盒内「本体」所在目录。

    skill/mcp 的本体是 workplace 下的同名子目录；sensor 的本体是 workplace
    根目录下的单个 <name>.py（没有独立子目录），故直接返回工作区根；
    graph 的本体是 workplace 下的同名文件夹；agentloop 的本体是 workplace
    根目录下的单个 <name>.yaml，同样直接返回工作区根。
    """
    if module_type in ("sensor", "agentloop"):
        return os.path.join(get_root(module_type), workplace_id)
    return os.path.join(get_root(module_type), workplace_id, name)


# ==========================================
# 🔧 通用 Git 操作辅助函数
# ==========================================
def unified_generate_diff(name: str, workplace_root: str, module_type: str) -> str:
    if module_type == "sensor":
        # sensor 本体是单文件：正式库 <name>.py ↔ 沙盒 <name>.py
        source_dir = os.path.join(SENSOR_EXTENSION_DIR, f"{name}.py")
        target_dir = os.path.join(workplace_root, f"{name}.py")
        label = "Sensor"
    elif module_type == "agentloop":
        # agentloop 本体是单文件：正式库 paradigms/<name>.yaml ↔ 沙盒 <name>.yaml
        source_dir = os.path.join(PARADIGMS_DIR, f"{name}.yaml")
        target_dir = os.path.join(workplace_root, f"{name}.yaml")
        label = "AgentLoop"
    elif module_type == "graph":
        # graph 本体是文件夹：正式库 graph/<name> ↔ 沙盒 <name>
        source_dir = os.path.join(GRAPHS_DIR, name)
        target_dir = os.path.join(workplace_root, name)
        label = "Graph"
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
    elif module_type == "agentloop":
        repo_root = PARADIGMS_DIR
        target = f"{name}.yaml"
    elif module_type == "graph":
        repo_root = GRAPHS_DIR
        target = name
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
# 🚀 编排入口（供路由薄委托）
# ==========================================
def scan_workplaces(module_type: str) -> list:
    """扫描指定加工厂的沙盒列表。"""
    workplaces = []
    root = get_root(module_type)
    if os.path.exists(root):
        for wid in os.listdir(root):
            w_path = os.path.join(root, wid)
            if not os.path.isdir(w_path):
                continue

            if module_type == "sensor":
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

            if module_type == "agentloop":
                # agentloop 工厂：本体是工作区根目录下的单个 <name>.yaml（不是同名子目录）
                item_name = "unknown"
                for item in sorted(os.listdir(w_path)):
                    if item.endswith((".yaml", ".yml")) and os.path.isfile(
                        os.path.join(w_path, item)
                    ):
                        item_name = os.path.splitext(item)[0]
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
                if module_type == "skill" and not os.path.exists(
                    os.path.join(item_path, "SKILL.md")
                ):
                    continue
                # graph 工厂：图本体是含 graph.json 的目录
                if module_type == "graph" and not os.path.exists(
                    os.path.join(item_path, "graph.json")
                ):
                    continue
                item_name = item
                break
            if item_name != "unknown":
                workplaces.append(
                    {"workplace_id": wid, "name": item_name, "status": "processing"}
                )
    return workplaces


def init_sandbox(
    module_type: str,
    name: str,
    is_upgrade: bool,
    goal: str,
    trace: bool,
    session_id: str,
) -> dict:
    try:
        if module_type == "mcp":
            msg, workplace_id = (
                mcp_upgrade_init(name, goal)
                if is_upgrade
                else mcp_improve_init(name, goal)
            )
        elif module_type == "sensor":
            msg, workplace_id = sensor_factory_init(name, is_upgrade, goal)
        elif module_type == "agentloop":
            msg, workplace_id = agentloop_factory_init(name, is_upgrade, goal)
        elif module_type == "graph":
            msg, workplace_id = graph_factory_init(name, is_upgrade, goal)
        else:
            msg, workplace_id = skill_improve_init(name, is_upgrade, goal)

        if not workplace_id:
            raise HTTPException(status_code=400, detail=msg)

        # trace2skill：记录来源会话 Token 快照，供盲测报告图标化展示"省下多少 token"
        # （快照失败不阻断建厂，报告侧会自然跳过 token 对比卡）
        if trace and session_id and module_type == "skill":
            record_trace_meta(workplace_id, session_id)

        return {"status": "success", "workplace_id": workplace_id, "message": msg}
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"初始化沙盒失败: {str(e)}")


def read_sandbox_files(
    module_type: str, workplace_id: str, name: str, filename: str
) -> dict:
    base_path = body_root(module_type, workplace_id, name)
    if not os.path.exists(base_path):
        raise HTTPException(status_code=404, detail="沙盒工作区不存在")

    if not filename:
        files_list = []
        for root_dir, dirs, files in os.walk(base_path):
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
                rel_path = os.path.relpath(os.path.join(root_dir, file), base_path)
                files_list.append(rel_path)
        return {"content": "", "attachments": sorted(files_list)}

    file_path = os.path.join(base_path, filename)
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            return {"content": f.read()}
    raise HTTPException(status_code=404, detail="文件不存在")


def write_sandbox_file(
    module_type: str, workplace_id: str, name: str, filename: str, content: str
) -> dict:
    try:
        file_path = os.path.join(body_root(module_type, workplace_id, name), filename)
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
        return {"status": "success", "message": "保存成功"}
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"保存文件失败: {str(e)}")


def read_sandbox_paradigm(workplace_id: str, name: str) -> dict:
    """读取沙盒内 AgentLoop 范式（YAML）并解析为结构化对象（供面板编辑器加载）。"""
    path = os.path.join(get_root("agentloop"), workplace_id, f"{name}.yaml")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="范式的沙盒文件不存在")
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except yaml.YAMLError as e:
        raise HTTPException(status_code=400, detail=f"YAML 解析失败: {e}")
    return {"name": name, "data": data if isinstance(data, dict) else {}}


def save_sandbox_paradigm(workplace_id: str, name: str, data: dict) -> dict:
    """把结构化对象序列化回沙盒内 <name>.yaml（面板编辑器的「保存到沙盒」）。"""
    path = os.path.join(get_root("agentloop"), workplace_id, f"{name}.yaml")
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            yaml.safe_dump(
                data if isinstance(data, dict) else {},
                f,
                allow_unicode=True,
                sort_keys=False,
                default_flow_style=False,
            )
    except yaml.YAMLError as e:
        raise HTTPException(status_code=400, detail=f"YAML 序列化失败: {e}")
    return {"status": "success", "message": "保存成功"}


def run_evals(module_type: str, workplace_id: str, name: str, session_id: str) -> dict:
    try:
        if module_type == "mcp":
            run_mcp_eval_background(workplace_id, name, session_id)
        elif module_type == "sensor":
            run_sensor_eval_background(workplace_id, name)
        else:
            run_skill_eval_background(
                workplace_id, name, session_id, new_iteration=True
            )
        return {"status": "success", "message": "盲测已启动"}
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"启动测试失败: {str(e)}")


def list_iterations(module_type: str, workplace_id: str) -> list:
    w_path = os.path.join(get_root(module_type), workplace_id)
    iters = []
    if os.path.exists(w_path):
        for item in os.listdir(w_path):
            match = re.match(r"iteration-(\d+)", item)
            if match:
                iters.append(int(match.group(1)))
    return sorted(iters)


def _latest_iteration(module_type: str, workplace_id: str) -> Optional[int]:
    iters = list_iterations(module_type, workplace_id)
    return max(iters) if iters else None


def read_eval_report(
    module_type: str, workplace_id: str, iteration: Optional[int]
) -> dict:
    """读取某轮评测的 HTML 报告（report.html）。报告即输出物，不再返回文件清单。"""
    w_path = os.path.join(get_root(module_type), workplace_id)
    if iteration is None:
        iteration = _latest_iteration(module_type, workplace_id)

    if iteration is not None:
        report_path = os.path.join(w_path, f"iteration-{iteration}", "report.html")
        if os.path.exists(report_path):
            with open(report_path, "r", encoding="utf-8") as f:
                return {"report_html": f.read()}
    return {"report_html": ""}


def read_benchmark(
    module_type: str, workplace_id: str, iteration: Optional[int]
) -> dict:
    """读取某轮体检的结构化结论（benchmark.json），供前端展示逐条判据与未覆盖项。"""
    w_path = os.path.join(get_root(module_type), workplace_id)
    if iteration is None:
        iteration = _latest_iteration(module_type, workplace_id)
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


def build_diff(module_type: str, workplace_id: str, name: str) -> dict:
    try:
        w_path = os.path.join(get_root(module_type), workplace_id)
        return {"diff_content": unified_generate_diff(name, w_path, module_type)}
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"生成 Diff 失败: {str(e)}")


def handle_request(
    module_type: str,
    workplace_id: str,
    name: str,
    is_approved: bool,
    reject_reason: Optional[str],
) -> dict:
    try:
        w_path = os.path.join(get_root(module_type), workplace_id)
        if not is_approved:
            reason_path = os.path.join(
                body_root(module_type, workplace_id, name), "REJECT_REASON.md"
            )
            with open(reason_path, "w", encoding="utf-8") as f:
                f.write(
                    f"# Human Code Review Feedback\n\n你的 Pull Request 被人类拒绝。"
                    f"请阅读以下修复建议并重新修改代码：\n\n{reject_reason}"
                )
            return {
                "status": "rejected",
                "message": "已将拒绝意见抛回沙盒，Agent可读取并继续调整。",
            }

        if module_type == "mcp":
            msg = mcp_request_handle(w_path, name, is_approved)
        elif module_type == "sensor":
            msg = sensor_request_handle(w_path, name, is_approved)
        elif module_type == "agentloop":
            msg = agentloop_request_handle(w_path, name, is_approved)
        elif module_type == "graph":
            msg = graph_request_handle(w_path, name, is_approved)
        else:
            msg = skill_request_handle(w_path, name, is_approved)
        return {"status": "success", "message": msg}
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"处理合并请求失败: {str(e)}")


def rollback(module_type: str, name: str) -> dict:
    try:
        msg = unified_rollback(name, module_type)
        if "失败" in msg or "异常" in msg:
            raise HTTPException(status_code=400, detail=msg)
        return {"status": "success", "message": msg}
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"强制回滚失败: {str(e)}")


def delete_workplace(workplace_id: str, module_type: str) -> dict:
    """前端手动彻底删除工厂沙盒。"""
    try:
        w_path = os.path.join(get_root(module_type), workplace_id)
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

    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"沙盒删除失败: {str(e)}")
