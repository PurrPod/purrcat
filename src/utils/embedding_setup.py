"""
嵌入模型校验与下载
检查 get_embedding_model() 指向的位置：
  - 是本地目录且包含 ONNX 模型与 tokenizer → 跳过
  - 否则 → 下载到 DATA_ROOT/embedding/
应用启动时由 ``ensure_embedding_model`` 后台检查：目录缺失或为空时自动下载；
已有其它版本的模型只提示、不自动覆盖，由记忆设置页显式更新。
部署页与安装脚本复用同一下载入口。

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
import shutil
import threading

from src.utils.config import DATA_ROOT
from src.utils.embedding_manifest import (
    ENV_MODEL_BASE,
    MODEL_NAME,
    MODEL_PROFILES,
    expected_files,
    file_matches,
    is_model_dir_complete,
    model_dir_state,
    resolve_sources,
    sha256_file,
    write_model_tag,
)

EMBEDDING_DIR = os.path.join(DATA_ROOT, "embedding")

__all__ = [
    "EMBEDDING_DIR",
    "MODEL_NAME",
    "cleanup_install_artifacts",
    "download_model",
    "ensure_embedding_model",
    "install_embedding_model",
]

_download_lock = threading.Lock()
_download_guard = threading.Lock()
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


def _download_profile(source: str, profile: dict, log, target_dir: str) -> None:
    base = source.rstrip("/")
    for rel, expected in expected_files(profile).items():
        dest = os.path.join(target_dir, rel.replace("/", os.sep))
        if _file_ok(dest, expected):
            continue
        if os.path.exists(dest):
            log(f"    ! 已有文件校验不通过，重新下载: {rel}")
        url = f"{base}/{MODEL_NAME}/resolve/main/{rel}"
        log(f"    ↓ {rel}")
        _download_file(url, dest, expected)


def download_model(endpoint: str | None = None, log=print) -> None:
    """下载入口：写盘串行化，避免启动自动下载与部署页同时写同一目录。"""
    with _download_guard:
        _download_model(endpoint, log)


def _download_model(
    endpoint: str | None = None, log=print, target_dir: str | None = None
) -> None:
    """同步下载嵌入模型到目标目录（默认 EMBEDDING_DIR）。

    endpoint=None 时按「自托管镜像 → hf-mirror → huggingface.co」依次尝试；
    传入 endpoint 则只尝试该源。供配置中心「部署」页（deploy_manager）与
    安装脚本（ensure_embedding_model）复用。
    """
    sources = resolve_sources(endpoint, os.environ.get(ENV_MODEL_BASE))
    target_dir = target_dir or EMBEDDING_DIR

    os.makedirs(target_dir, exist_ok=True)
    log(f"    模型: {MODEL_NAME}")
    log(f"    目录: {target_dir}")

    errors = []
    for profile in MODEL_PROFILES:
        # 已经完整（比如上次下的是 fp32）就不再下第二个 profile
        if _model_exists(target_dir):
            return
        for source in sources:
            try:
                _download_profile(source, profile, log, target_dir)
                write_model_tag(target_dir)
                if _model_exists(target_dir):
                    log(f"    ✓ 下载完成（来源: {source}）")
                    return
            except Exception as e:
                errors.append(f"{source}: {e}")
                log(f"    ! 该源失败，换下一个: {e}")

    raise RuntimeError("嵌入模型下载失败:\n" + "\n".join(errors))


def cleanup_install_artifacts() -> None:
    """清理上次中断留下的暂存/备份目录；换名中断时优先恢复完整目录。"""
    staging = EMBEDDING_DIR + ".next"
    backup = EMBEDDING_DIR + ".old"
    if not os.path.isdir(EMBEDDING_DIR):
        for candidate in (staging, backup):
            if is_model_dir_complete(candidate):
                os.replace(candidate, EMBEDDING_DIR)
                break
    for path in (staging, backup):
        shutil.rmtree(path, ignore_errors=True)


def install_embedding_model(endpoint: str | None = None, log=print) -> dict:
    """下载到暂存目录，校验通过后原子替换现有模型。

    替换失败时把旧目录改名回原位；成功后删除备份，并清空编码器缓存，
    避免进程继续用旧权重。
    """
    from src.utils.local_embedding import reset_embedder_cache

    staging = EMBEDDING_DIR + ".next"
    backup = EMBEDDING_DIR + ".old"
    with _download_guard:
        shutil.rmtree(staging, ignore_errors=True)
        shutil.rmtree(backup, ignore_errors=True)
        os.makedirs(staging, exist_ok=True)
        try:
            _download_model(endpoint, log, target_dir=staging)
            if not is_model_dir_complete(staging):
                raise RuntimeError("下载完成但模型目录不完整")
            # 先释放进程内编码器，Windows 上否则可能因文件句柄无法改名
            reset_embedder_cache()
            if os.path.isdir(EMBEDDING_DIR):
                os.replace(EMBEDDING_DIR, backup)
            try:
                os.replace(staging, EMBEDDING_DIR)
            except Exception:
                if os.path.isdir(backup) and not os.path.isdir(EMBEDDING_DIR):
                    os.replace(backup, EMBEDDING_DIR)
                raise
        finally:
            shutil.rmtree(staging, ignore_errors=True)

        shutil.rmtree(backup, ignore_errors=True)
        reset_embedder_cache()
        return {"installed": True, "dir": EMBEDDING_DIR, "model": MODEL_NAME}


def ensure_embedding_model() -> None:
    """幂等检查嵌入模型：仅在缺失或为空时后台下载。

    旧版本模型不自动覆盖（避免用户无感知地丢掉正在使用的权重），
    由记忆设置页显式触发更新。
    """
    from src.utils.config import get_embedding_model, is_data_root_configured

    # 数据根目录尚未配置（首启引导还没完成）时不下载，
    # 否则会下到默认位置，等用户选好数据盘后还得重下
    if not is_data_root_configured():
        print(
            "[*] 数据根目录尚未配置，跳过嵌入模型下载（可在应用内 配置中心 → 部署 页安装）"
        )
        return

    cleanup_install_artifacts()

    target = get_embedding_model()
    state = model_dir_state(target)
    if state == "current":
        return
    if state == "outdated":
        print(
            f"[!] 嵌入模型不是当前版本（需要 {MODEL_NAME}），已跳过自动替换；"
            "请在 配置中心 → 记忆 页更新"
        )
        return

    if _downloading_flag.is_set():
        return

    with _download_lock:
        if _downloading_flag.is_set():
            return
        _downloading_flag.set()

    def _do_download():
        try:
            print("[*] 正在后台下载嵌入模型（int8 约 135MB）...")
            download_model()
            print("[+] 嵌入模型下载完成！")
            # 依赖检查可能已写入「嵌入模型未就绪」请求，下载完成后重新核对并清除
            from src.utils.dependency_check import check_and_warn_dependencies

            check_and_warn_dependencies()
        except Exception as e:
            print(f"[!] 嵌入模型下载失败: {e}")
            print("    可稍后在应用内 配置中心 → 部署 页重试")
        finally:
            _downloading_flag.clear()

    threading.Thread(target=_do_download, daemon=True).start()
