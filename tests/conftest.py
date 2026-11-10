from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

# 目录即层级：新增用例不必记得打标记，按所在目录自动归类。
_LAYER_MARKERS = {
    "l0": pytest.mark.l0,
    "l1": pytest.mark.l1,
    "l2": pytest.mark.l2,
    "l3": pytest.mark.l3,
}


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        parts = set(Path(str(item.path)).parts)
        marker = next(
            (mark for name, mark in _LAYER_MARKERS.items() if name in parts),
            pytest.mark.l0,
        )
        item.add_marker(marker)


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO_ROOT
