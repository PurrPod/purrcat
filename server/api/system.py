import platform
import shutil
import subprocess
from typing import Optional

import docker
from docker.errors import DockerException, ImageNotFound
from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from src.utils.config import get_container_engine, set_container_engine

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
    engine: str = "podman"


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
            [engine, "--version"],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode == 0:
            return result.stdout.strip()
        return None
    except Exception:
        return None


def _check_engine_running(engine: str) -> bool:
    try:
        if engine == "podman":
            result = subprocess.run(
                ["podman", "machine", "list"],
                capture_output=True,
                text=True,
                timeout=10
            )
            return result.returncode == 0
        else:
            result = subprocess.run(
                ["docker", "info"],
                capture_output=True,
                text=True,
                timeout=10
            )
            return result.returncode == 0
    except Exception:
        return False


@router.get("/env/detect", response_model=DetectResponse)
def detect_environment():
    os_name = platform.system()
    
    has_docker = shutil.which("docker") is not None
    has_podman = shutil.which("podman") is not None
    
    recommend_engine = "docker"
    recommend_reason = "Docker 是最普及的容器引擎。"

    if os_name == "Windows" and not has_docker:
        recommend_engine = "podman"
        recommend_reason = "检测到您是 Windows 用户且未安装 Docker Desktop。强烈推荐使用轻量级、无广告、免安装臃肿桌面的 Podman。"
    elif os_name == "Darwin" and not has_docker:
        recommend_engine = "podman"
        recommend_reason = "推荐使用轻量级的 Podman 来节省 Mac 的内存资源。"
    elif has_podman and not has_docker:
        recommend_engine = "podman"
        recommend_reason = "检测到您已安装 Podman。"
    elif has_podman and has_docker:
        recommend_engine = "docker"
        recommend_reason = "检测到您同时安装了 Docker 和 Podman，默认推荐使用 Docker。"

    return DetectResponse(
        os=os_name,
        installed={
            "docker": has_docker,
            "podman": has_podman
        },
        recommend=recommend_engine,
        recommend_reason=recommend_reason
    )


@router.get("/env-status", response_model=EnvStatusResponse)
def get_environment_status():
    try:
        engine = get_container_engine()
        version = _get_engine_version(engine)
        is_running = _check_engine_running(engine)
        
        if not is_running:
            return EnvStatusResponse(
                is_ready=False,
                engine=engine,
                engine_version=version,
                error=f"{engine.capitalize()} 引擎未运行，请先启动 {engine.capitalize()}"
            )
        
        return EnvStatusResponse(
            is_ready=True,
            engine=engine,
            engine_version=version,
            error=None
        )
    except RuntimeError as e:
        return EnvStatusResponse(
            is_ready=False,
            engine=None,
            engine_version=None,
            error=str(e)
        )
    except Exception as e:
        return EnvStatusResponse(
            is_ready=False,
            engine=None,
            engine_version=None,
            error=f"环境检测失败: {str(e)}"
        )


@router.get("/env/status")
def get_env_status_simple():
    has_podman = shutil.which("podman") is not None
    has_docker = shutil.which("docker") is not None
    return {
        "ready": has_podman or has_docker,
        "engine": "podman" if has_podman else ("docker" if has_docker else None),
        "has_podman": has_podman,
        "has_docker": has_docker
    }


@router.get("/image-status", response_model=ImageStatusResponse)
def get_image_status(image_name: str = "my_agent_env:latest"):
    try:
        engine = get_container_engine()
        client = docker.from_env()
        
        try:
            client.images.get(image_name)
            return ImageStatusResponse(
                exists=True,
                image_name=image_name,
                error=None
            )
        except ImageNotFound:
            return ImageStatusResponse(
                exists=False,
                image_name=image_name,
                error=f"镜像 {image_name} 不存在"
            )
    except RuntimeError as e:
        return ImageStatusResponse(
            exists=False,
            image_name=image_name,
            error=str(e)
        )
    except DockerException as e:
        return ImageStatusResponse(
            exists=False,
            image_name=image_name,
            error=f"{engine.capitalize()} 连接失败: {str(e)}"
        )
    except Exception as e:
        return ImageStatusResponse(
            exists=False,
            image_name=image_name,
            error=f"镜像检测失败: {str(e)}"
        )


def _pull_image_task(image_name: str):
    try:
        client = docker.from_env()
        print(f"🚀 开始拉取镜像: {image_name}")
        client.images.pull(image_name)
        print(f"✅ 镜像拉取成功: {image_name}")
    except Exception as e:
        print(f"❌ 镜像拉取失败: {e}")


@router.post("/pull-image", response_model=PullImageResponse)
def pull_image(request: PullImageRequest, background_tasks: BackgroundTasks):
    try:
        engine = get_container_engine()
        
        try:
            client = docker.from_env()
            client.images.get(request.image_name)
            return PullImageResponse(
                status="exists",
                message=f"镜像 {request.image_name} 已存在，无需拉取"
            )
        except ImageNotFound:
            pass
        
        background_tasks.add_task(_pull_image_task, request.image_name)
        
        return PullImageResponse(
            status="started",
            message=f"已开始后台拉取镜像 {request.image_name}，请稍候..."
        )
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except DockerException as e:
        raise HTTPException(
            status_code=500,
            detail=f"{engine.capitalize()} 连接失败: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"镜像拉取启动失败: {str(e)}"
        )


def _install_task(engine: str):
    global _install_progress, _install_status, _install_error, _selected_engine
    
    _selected_engine = engine
    
    try:
        _install_status = "installing"
        _install_progress = 10
        
        set_container_engine(engine)
        
        if engine == "podman":
            from scripts.setup_env import setup
            success, message = setup()
        elif engine == "docker":
            if shutil.which("docker"):
                success = True
                message = "Docker 已安装"
            else:
                success = False
                message = "Docker 未安装，请手动安装 Docker Desktop"
        
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
            progress=_install_progress
        )
    
    background_tasks.add_task(_install_task, request.engine)
    
    return InstallStatusResponse(
        status="started",
        message=f"开始安装 {request.engine} 环境...",
        progress=0
    )


@router.get("/env/install/status", response_model=InstallStatusResponse)
def get_install_status():
    return InstallStatusResponse(
        status=_install_status,
        message=_install_error if _install_status == "failed" else "安装进行中...",
        progress=_install_progress
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
                "podman": shutil.which("podman") is not None,
                "docker": shutil.which("docker") is not None
            },
            "selected_engine": _selected_engine
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))