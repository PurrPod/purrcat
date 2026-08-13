import platform
import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Optional

import docker
from docker.errors import DockerException, ImageNotFound
from fastapi import APIRouter, BackgroundTasks, HTTPException, UploadFile, File
from pydantic import BaseModel

from src.utils.config import get_container_engine, set_container_engine, TRACKER_DIR, BUFFER_DIR
from src.model.manager.usage_tracer import usage_tracer

router = APIRouter(prefix="/api/system", tags=["System Environment"])


class EnvStatusResponse(BaseModel):
    is_ready: bool
    engine: Optional[str] = None
    engine_version: Optional[str] = None
    error: Optional[str] = None


class ImageStatusResponse(BaseModel):
    exists: bool
    image_name: str
    error: Optional[str] = None


class PullImageRequest(BaseModel):
    image_name: str


class PullImageResponse(BaseModel):
    status: str
    message: str


class InstallStatusResponse(BaseModel):
    status: str
    message: str
    progress: int = 0


class InstallRequest(BaseModel):
    engine: str = "docker"


class DetectResponse(BaseModel):
    os: str
    installed: dict[str, bool]
    recommend: str
    recommend_reason: str


_install_progress = 0
_install_status = "idle"
_install_error = None
_selected_engine = None


def _get_engine_version(engine: str) -> Optional[str]:
    try:
        result = subprocess.run(
            [engine, "--version"], capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            return result.stdout.strip()
        return None
    except Exception:
        return None


def _check_engine_running(engine: str) -> bool:
    try:
        result = subprocess.run(
            ["docker", "info"], capture_output=True, text=True, timeout=10
        )
        return result.returncode == 0
    except Exception:
        return False


@router.get("/env/detect", response_model=DetectResponse)
def detect_environment():
    os_name = platform.system()

    has_docker = shutil.which("docker") is not None

    if has_docker:
        recommend_engine = "docker"
        recommend_reason = "检测到已安装 Docker。"
    else:
        recommend_engine = "docker"
        recommend_reason = (
            "未检测到 Docker。请先安装 Docker Desktop：\n"
            "https://docs.docker.com/get-docker/\n"
            "Windows 需启用 WSL2，安装后重启系统。"
        )

    return DetectResponse(
        os=os_name,
        installed={"docker": has_docker},
        recommend=recommend_engine,
        recommend_reason=recommend_reason,
    )


@router.get("/env-status", response_model=EnvStatusResponse)
def get_environment_status():
    try:
        engine = get_container_engine()
        version = _get_engine_version(engine)
        if not _check_engine_running(engine):
            return EnvStatusResponse(
                is_ready=False,
                engine=engine,
                engine_version=version,
                error="Docker daemon 未启动，请启动 Docker Desktop。",
            )
        return EnvStatusResponse(
            is_ready=True, engine=engine, engine_version=version
        )
    except RuntimeError as e:
        return EnvStatusResponse(is_ready=False, error=str(e))


@router.get("/env/status")
def get_env_status_simple():
    has_docker = shutil.which("docker") is not None
    return {
        "ready": has_docker,
        "engine": "docker" if has_docker else None,
        "has_docker": has_docker,
    }


@router.get("/image-status", response_model=ImageStatusResponse)
def get_image_status(image_name: str = "my_agent_env:latest"):
    try:
        engine = get_container_engine()
        client = docker.from_env()
        try:
            client.images.get(image_name)
            return ImageStatusResponse(exists=True, image_name=image_name)
        except ImageNotFound:
            return ImageStatusResponse(exists=False, image_name=image_name)
    except RuntimeError as e:
        return ImageStatusResponse(
            exists=False, image_name=image_name, error=str(e)
        )
    except DockerException as e:
        return ImageStatusResponse(
            exists=False, image_name=image_name, error=f"Docker 连接失败: {str(e)}"
        )


def _pull_image_task(image_name: str):
    import time as _t
    global _install_progress, _install_status, _install_error
    _install_status = "installing"
    _install_progress = 5
    try:
        client = docker.from_env()
        client.images.pull(image_name)
        _install_progress = 100
        _install_status = "completed"
        _install_error = None
    except Exception as e:
        _install_status = "failed"
        _install_error = str(e)


@router.post("/image/pull", response_model=PullImageResponse)
def pull_image(request: PullImageRequest, background_tasks: BackgroundTasks):
    try:
        engine = get_container_engine()
        background_tasks.add_task(_pull_image_task, request.image_name)

        return PullImageResponse(
            status="started",
            message=f"已开始后台拉取镜像 {request.image_name}，请稍候...",
        )
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except DockerException as e:
        raise HTTPException(
            status_code=500, detail=f"Docker 连接失败: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"镜像拉取启动失败: {str(e)}")


def _install_task(engine: str):
    global _install_progress, _install_status, _install_error, _selected_engine

    _selected_engine = engine

    try:
        _install_status = "installing"
        _install_progress = 10

        set_container_engine(engine)

        if shutil.which("docker"):
            success = True
            message = "Docker 已安装"
        else:
            success = False
            message = (
                "Docker 未安装，请手动安装 Docker Desktop。\n"
                "安装指引: https://docs.docker.com/get-docker/"
            )

        if success:
            _install_status = "completed"
            _install_progress = 100
            _install_error = None
        else:
            _install_status = "failed"
            _install_error = message
    except Exception as e:
        _install_status = "failed"
        _install_error = str(e)


@router.post("/env/install", response_model=InstallStatusResponse)
def trigger_install(request: InstallRequest, background_tasks: BackgroundTasks):
    global _install_status

    if _install_status == "installing":
        return InstallStatusResponse(
            status="installing",
            message="正在安装中，请稍候...",
            progress=_install_progress,
        )

    background_tasks.add_task(_install_task, request.engine)

    return InstallStatusResponse(
        status="started", message=f"开始安装 {request.engine} 环境...", progress=0
    )


@router.get("/env/install/status", response_model=InstallStatusResponse)
def get_install_status():
    return InstallStatusResponse(
        status=_install_status,
        message=_install_error if _install_status == "failed" else "安装进行中...",
        progress=_install_progress,
    )


@router.get("/container-engine")
def get_container_engine_info():
    try:
        engine = get_container_engine()
        version = _get_engine_version(engine)

        return {
            "engine": engine,
            "version": version,
            "available_engines": {
                "docker": shutil.which("docker") is not None,
            },
            "selected_engine": _selected_engine,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# --- 🌟 文件上传到 buffer 目录 ---
UPLOAD_BUFFER_DIR = Path(BUFFER_DIR) / "upload"


@router.post("/agent/upload")
async def upload_buffer_file(
    file: UploadFile = File(...),
    filename: Optional[str] = None,
):
    """上传单个文件到 agent_vm/.buffer/upload 目录，供 Agent 读取。"""
    import aiofiles

    UPLOAD_BUFFER_DIR.mkdir(parents=True, exist_ok=True)
    save_name = filename or file.filename or f"upload_{uuid.uuid4().hex[:8]}"
    dest = UPLOAD_BUFFER_DIR / save_name

    async with aiofiles.open(dest, "wb") as f:
        while chunk := await file.read(1024 * 1024):
            await f.write(chunk)

    return {
        "success": True,
        "saved_path": str(dest),
        "size_bytes": dest.stat().st_size,
        "agent_path": str(dest.resolve()),
    }


# --- 🌟 使用量跟踪器 API ---


@router.get("/usage")
def get_usage_stats():
    """返回使用量跟踪的聚合统计（总 tokens / 调用次数 / 最近记录）"""
    try:
        return usage_tracer.summarize()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/usage/recent")
def get_recent_usage(limit: int = 30):
    """最近 N 条使用量记录"""
    try:
        return usage_tracer.recent(limit=limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/usage/clear")
def clear_usage_records():
    """清空使用量记录（保留目录结构）"""
    try:
        removed = usage_tracer.clear()
        return {"removed": removed}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
