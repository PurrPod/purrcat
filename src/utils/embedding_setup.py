"""
嵌入模型校验与下载
检查 get_embedding_model() 指向的位置：
  - 是本地目录且包含 ONNX 模型与 tokenizer → 跳过
  - 否则 → 下载到 DATA_ROOT/embedding/
应用内不再启动时自动下载（与部署页并发写会互相踩踏），
下载入口：安装脚本（ensure_embedding_model）与 配置中心 → 部署 页（deploy_manager）

注意：下载的是原 sentence-transformers 模型的 ONNX 导出（同一份权重、同一个
tokenizer），运行时用 onnxruntime 推理，不再需要 torch / transformers。

下载走 curl_cffi（项目已有依赖）直连多源，不需要 huggingface_hub：
  1. 环境变量 PURRCAT_EMBEDDING_BASE（自托管镜像，HF 兼容目录结构）
  2. https://hf-mirror.com
  3. https://huggingface.co
按文件 SHA256 校验，坏包会自动换下一个源。

清单与完整性判定在 embedding_manifest；本模块负责下载与启动期幂等。
"""

import os
import threading

from src.utils.config import DATA_ROOT
from src.utils.embedding_manifest import (
    ENV_MODEL_BASE,
    MODEL_NAME,
    MODEL_PROFILES,
    expected_files,
    file_matches,
    is_model_dir_complete,
    resolve_sources,
    sha256_file,
)

EMBEDDING_DIR = os.path.join(DATA_ROOT, "embedding")

__all__ = [
    "EMBEDDING_DIR",
    "MODEL_NAME",
    "download_model",
    "ensure_embedding_model",
]

_download_lock = threading.Lock()
_downloading_flag = threading.Event()


def _model_exists(local_dir: str) -> bool:
    """判断目录是否包含 ONNX 模型与 tokenizer 文件"""
    return is_model_dir_complete(local_dir)


def _sha256(path: str) -> str:
    return sha256_file(path)


def _file_ok(path: str, expected: str) -> bool:
    return file_matches(path, expected)


def _download_file(url: str, dest: str, expected: str) -> None:
    """下载单文件到 dest，写入 .part 并校验 SHA256，坏包直接丢弃。"""
    from curl_cffi import requests

    os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
    tmp = dest + ".part"
    resp = requests.get(url, impersonate="chrome", timeout=(10, 600), stream=True)
    try:
        resp.raise_for_status()
        with open(tmp, "wb") as f:
            for chunk in resp.iter_content(1024 * 1024):
                if chunk:
                    f.write(chunk)
    finally:
        resp.close()

    if _sha256(tmp) != expected:
        os.remove(tmp)
        raise RuntimeError(f"SHA256 校验失败: {url}")

    os.replace(tmp, dest)


def _download_profile(source: str, profile: dict, log) -> None:
    base = source.rstrip("/")
    for rel, expected in expected_files(profile).items():
        dest = os.path.join(EMBEDDING_DIR, rel.replace("/", os.sep))
        if _file_ok(dest, expected):
            continue
        if os.path.exists(dest):
            log(f"    ! 已有文件校验不通过，重新下载: {rel}")
        url = f"{base}/{MODEL_NAME}/resolve/main/{rel}"
        log(f"    ↓ {rel}")
        _download_file(url, dest, expected)


def download_model(endpoint: str | None = None, log=print) -> None:
    """同步下载嵌入模型到 EMBEDDING_DIR。

    endpoint=None 时按「自托管镜像 → hf-mirror → huggingface.co」依次尝试；
    传入 endpoint 则只尝试该源。供配置中心「部署」页（deploy_manager）与
    安装脚本（ensure_embedding_model）复用。
    """
    sources = resolve_sources(endpoint, os.environ.get(ENV_MODEL_BASE))

    os.makedirs(EMBEDDING_DIR, exist_ok=True)
    log(f"    模型: {MODEL_NAME}")
    log(f"    目录: {EMBEDDING_DIR}")

    errors = []
    for profile in MODEL_PROFILES:
        # 已经完整（比如上次下的是 fp32）就不再下第二个 profile
        if _model_exists(EMBEDDING_DIR):
            return
        for source in sources:
            try:
                _download_profile(source, profile, log)
                if _model_exists(EMBEDDING_DIR):
                    log(f"    ✓ 下载完成（来源: {source}）")
                    return
            except Exception as e:
                errors.append(f"{source}: {e}")
                log(f"    ! 该源失败，换下一个: {e}")

    raise RuntimeError("嵌入模型下载失败:\n" + "\n".join(errors))


def ensure_embedding_model() -> None:
    """幂等检查嵌入模型，不存在则后台下载（不阻塞启动）。"""
    from src.utils.config import get_embedding_model, is_data_root_configured

    # 数据根目录尚未配置（首启引导还没完成）时不下载，
    # 否则会下到默认位置，等用户选好数据盘后还得重下
    if not is_data_root_configured():
        print(
            "[*] 数据根目录尚未配置，跳过嵌入模型下载（可在应用内 配置中心 → 部署 页安装）"
        )
        return

    target = get_embedding_model()

    # 1) 如果 embedding 配置的是绝对本地路径且已经存在文件，直接跳过
    if os.path.isabs(target) and _model_exists(target):
        return

    # 2) 如果 target 就是我们的本地 EMBEDDING_DIR 并且存在，也跳过
    if os.path.abspath(target) == os.path.abspath(EMBEDDING_DIR) and _model_exists(
        EMBEDDING_DIR
    ):
        return

    # 3) 如果 EMBEDDING_DIR 本身已完整，也跳过
    if _model_exists(EMBEDDING_DIR):
        return

    if _downloading_flag.is_set():
        return

    with _download_lock:
        if _downloading_flag.is_set():
            return
        _downloading_flag.set()

    def _do_download():
        try:
            print("[*] 首次运行，正在后台下载嵌入模型（int8 约 113MB）...")
            download_model()
            print("[+] 嵌入模型下载完成！")
        except Exception as e:
            print(f"[!] 嵌入模型下载失败: {e}")
            print("    可稍后在应用内 配置中心 → 部署 页重试")
        finally:
            _downloading_flag.clear()

    threading.Thread(target=_do_download, daemon=True).start()
