"""
嵌入模型自动下载与校验
检查 get_embedding_model() 指向的位置：
  - 是本地目录且包含 config.json → 跳过
  - 否则 → 后台线程下载到 BASE_DIR/embedding/
"""

import os
import threading

from src.utils.config import DATA_ROOT

MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
EMBEDDING_DIR = os.path.join(DATA_ROOT, "embedding")

_download_lock = threading.Lock()
_downloading_flag = threading.Event()


def _model_exists(local_dir: str) -> bool:
    """判断目录是否包含 SentenceTransformer 的完整权重文件"""
    if not os.path.isdir(local_dir):
        return False
    required = ["config.json", "modules.json", "tokenizer.json"]
    if not all(os.path.exists(os.path.join(local_dir, f)) for f in required):
        return False
    # 权重文件（新版 safetensors 或旧版 bin），任一存在才视为完整，避免下载中断误判
    weights = ["model.safetensors", "pytorch_model.bin"]
    return any(os.path.exists(os.path.join(local_dir, f)) for f in weights)


def ensure_embedding_model() -> None:
    """幂等检查嵌入模型，不存在则后台下载（不阻塞启动）。"""
    from src.utils.config import get_embedding_model, is_data_root_configured

    # 数据根目录尚未配置（首启引导还没完成）时不下载，
    # 否则会下到默认位置，等用户选好数据盘后还得重下
    if not is_data_root_configured():
        print("[*] 数据根目录尚未配置，跳过嵌入模型下载（配置好并重启后会自动下载）")
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

    # 3) 如果 EMBEDDING_DIR 本身已完整，也跳过（此时 SentenceTransformer 会按需 fallback）
    if _model_exists(EMBEDDING_DIR):
        return

    if _downloading_flag.is_set():
        return

    with _download_lock:
        if _downloading_flag.is_set():
            return
        _downloading_flag.set()

    def _download_from(endpoint: str | None) -> None:
        """从指定 HF 端点下载模型。endpoint=None 走官方 huggingface.co。"""
        # huggingface_hub 在 import 时固化 HF_ENDPOINT；若已被 import 过
        # （如 sentence_transformers 提前加载过），清缓存强制按新端点重载
        if endpoint:
            os.environ["HF_ENDPOINT"] = endpoint
            import sys

            for mod in list(sys.modules):
                if mod.startswith("huggingface_hub"):
                    del sys.modules[mod]

        from huggingface_hub import snapshot_download

        os.makedirs(EMBEDDING_DIR, exist_ok=True)
        snapshot_download(
            repo_id=MODEL_NAME,
            local_dir=EMBEDDING_DIR,
            ignore_patterns=[
                "*.ot",
                "*.h5",
                "*.msgpack",
                "*.flax",
                "*.tensorflow",
                "*.tf",
                "*.tflite",
            ],
        )

    def _do_download():
        try:
            print("[*] 首次运行，正在后台下载嵌入模型（~120MB）...")
            print(f"    模型: {MODEL_NAME}")
            print(f"    目录: {EMBEDDING_DIR}")
            _download_from(None)
            print("[+] 嵌入模型下载完成！")
        except Exception as e:
            # 直连 huggingface.co 失败（国内网络常态）→ 自动切 hf-mirror.com 镜像重试，
            # 否则嵌入模型永远缺失，向量经验库会一直写不进数据
            print(f"[!] 直连 huggingface.co 下载失败: {e}")
            print("[*] 切换 hf-mirror.com 镜像重试...")
            try:
                _download_from("https://hf-mirror.com")
                print("[+] 嵌入模型（镜像）下载完成！")
            except Exception as e2:
                print(f"[!] 嵌入模型下载失败: {e2}")
                print("    你可以稍后手动执行: purrcat setup")
        finally:
            _downloading_flag.clear()

    threading.Thread(target=_do_download, daemon=True).start()
