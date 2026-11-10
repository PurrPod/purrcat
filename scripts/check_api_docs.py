#!/usr/bin/env python3
"""校验 docs/api 下的生成物是否与 FastAPI 契约一致。

生成物由 ``scripts/gen_api_docs.py`` 从 ``create_app().openapi()`` 产出；
本脚本只做比较，绝不改写文件，漂移时非零退出供 CI 拦截。

用法：
    python scripts/check_api_docs.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT_DIR = Path(__file__).resolve().parent
for _path in (str(ROOT), str(SCRIPT_DIR)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import gen_api_docs  # noqa: E402


def main() -> int:
    stale = gen_api_docs.check_documents()

    if not stale:
        print("[OK] docs/api/openapi.json 与 openapi.md 已与 FastAPI 契约一致")
        return 0

    print("[ERROR] 生成物过期，请运行 uv run python scripts/gen_api_docs.py")
    for path in stale:
        print(f"  {gen_api_docs.relative_path(path)}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
