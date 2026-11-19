"""一次性重建记忆向量库（更换嵌入模型后执行）。

用法：
    uv run python scripts/reindex_memory.py

执行前先停掉后端（npm run dev / main.py），否则两个进程会同时写 Chroma。
只重写向量，不改事件 / 经验 / 图谱的原始数据。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# 直接运行脚本时把仓库根目录加入导入路径
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.memory.config import CHROMADB_PERSIST_DIRECTORY
from src.memory.reindex import rebuild_vector_index


def main() -> int:
    print(f"向量目录：{CHROMADB_PERSIST_DIRECTORY}")
    report = rebuild_vector_index(log=print)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
