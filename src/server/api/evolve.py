"""进化工厂路由：只声明路由与请求模型，编排在 evolve_service。"""

from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

from src.server.api import evolve_service

router = APIRouter(prefix="/api/evolve", tags=["Evolution Factory"])


# ==========================================
# 📌 Pydantic 校验模型
# ==========================================
class InitReq(BaseModel):
    type: str = "skill"
    name: str
    is_upgrade: bool
    goal: str = ""  # 本次构建目标（写入 GOAL.md 并嵌入 GUIDE.md）
    # trace2skill 入口：为 true 时把来源会话的 Token 快照写入沙盒 trace_meta.json
    trace: bool = False
    session_id: str = ""


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


class ParadigmSaveReq(BaseModel):
    data: dict


@router.get("/list")
def list_workplaces(type: str = "skill"):
    """扫描指定加工厂的沙盒列表"""
    return evolve_service.scan_workplaces(type)


@router.post("/init")
def init_sandbox_api(req: InitReq):
    return evolve_service.init_sandbox(
        req.type, req.name, req.is_upgrade, req.goal, req.trace, req.session_id
    )


@router.get("/file")
def get_file_api(workplace_id: str, name: str, type: str = "skill", filename: str = ""):
    return evolve_service.read_sandbox_files(type, workplace_id, name, filename)


@router.put("/file")
def update_file_api(
    workplace_id: str, name: str, filename: str, req: FileUpdateReq, type: str = "skill"
):
    return evolve_service.write_sandbox_file(
        type, workplace_id, name, filename, req.content
    )


@router.get("/paradigm")
def get_sandbox_paradigm_api(workplace_id: str, name: str):
    """读取沙盒内 AgentLoop 范式（YAML）并解析为结构化对象（供面板编辑器加载）。"""
    return evolve_service.read_sandbox_paradigm(workplace_id, name)


@router.post("/paradigm")
def save_sandbox_paradigm_api(workplace_id: str, name: str, req: ParadigmSaveReq):
    """把结构化对象序列化回沙盒内 <name>.yaml（面板编辑器的「保存到沙盒」）。"""
    return evolve_service.save_sandbox_paradigm(workplace_id, name, req.data)


@router.post("/test/run")
def run_evals_api(req: TestRunReq):
    return evolve_service.run_evals(
        req.type, req.workplace_id, req.name, req.session_id
    )


@router.get("/test/iterations")
def list_iterations_api(workplace_id: str, type: str = "skill"):
    return evolve_service.list_iterations(type, workplace_id)


@router.get("/test/report")
def get_eval_report_api(
    workplace_id: str, name: str, type: str = "skill", iteration: Optional[int] = None
):
    """读取某轮评测的 HTML 报告（report.html）。报告即输出物，不再返回文件清单。"""
    return evolve_service.read_eval_report(type, workplace_id, iteration)


@router.get("/test/benchmark")
def get_benchmark_api(
    workplace_id: str, type: str = "sensor", iteration: Optional[int] = None
):
    """读取某轮体检的结构化结论（benchmark.json），供前端展示逐条判据与未覆盖项"""
    return evolve_service.read_benchmark(type, workplace_id, iteration)


@router.get("/diff")
def get_diff_api(workplace_id: str, name: str, type: str = "skill"):
    return evolve_service.build_diff(type, workplace_id, name)


@router.post("/handle")
def handle_request_api(req: HandleReq):
    return evolve_service.handle_request(
        req.type, req.workplace_id, req.name, req.is_approved, req.reject_reason
    )


@router.post("/rollback")
def rollback_skill_api(req: RollbackReq):
    return evolve_service.rollback(req.type, req.name)


@router.delete("/workplace/{workplace_id}")
def delete_workplace_api(workplace_id: str, type: str = "skill"):
    """前端手动彻底删除工厂沙盒"""
    return evolve_service.delete_workplace(workplace_id, type)
