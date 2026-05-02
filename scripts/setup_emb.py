#!/usr/bin/env python3
"""
Embedding 模型预下载脚本
将 sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 下载到本地 embedding/ 目录
"""

import os
import sys


def main():
    script_path = os.path.abspath(__file__)
    base_dir = os.path.dirname(os.path.dirname(script_path))
    embedding_dir = os.path.join(base_dir, "embedding")
    model_name = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

    print(f"🐱 开始下载 Embedding 模型...")
    print(f"📦 模型: {model_name}")
    print(f"📂 目标目录: {embedding_dir}")

    if os.path.exists(embedding_dir) and os.listdir(embedding_dir):
        print(f"✅ 模型已存在于 {embedding_dir}，跳过下载。")
        return

    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        print("❌ 缺少 huggingface_hub 库，正在安装...")
        os.system(f"{sys.executable} -m pip install huggingface_hub -q")
        from huggingface_hub import snapshot_download

    os.makedirs(embedding_dir, exist_ok=True)

    print("⏳ 首次下载可能需要几分钟，请耐心等待...")
    snapshot_download(
        repo_id=model_name,
        local_dir=embedding_dir,
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

    print(f"✅ Embedding 模型下载完成！")
    print(f"📂 模型路径: {embedding_dir}")


if __name__ == "__main__":
    main()
