#!/usr/bin/env python3
"""
Embedding Model Pre-download Script
Downloads sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 to local embedding/ directory
"""

import os
import sys


def main():
    script_path = os.path.abspath(__file__)
    base_dir = os.path.dirname(os.path.dirname(script_path))
    embedding_dir = os.path.join(base_dir, "embedding")
    model_name = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

    print(f"[+] Starting Embedding model download...")
    print(f"[*] Model: {model_name}")
    print(f"[*] Target directory: {embedding_dir}")

    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        print("[-] huggingface_hub not found, installing...")
        os.system(f"{sys.executable} -m pip install huggingface_hub -q")
        from huggingface_hub import snapshot_download

    os.makedirs(embedding_dir, exist_ok=True)

    print("[*] First download may take a few minutes, please wait...")
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

    print(f"[+] Embedding model download complete!")
    print(f"[*] Model path: {embedding_dir}")


if __name__ == "__main__":
    main()