"""Config API 的可纯化校验分支（SPEC-020）。

覆盖 ACP 端口、数据根、Markdown 文件名、JSON 读取与 sandbox registry
归一化；拆分后路由行为与错误文案必须逐字不变。
"""

from __future__ import annotations

import json
import os

import pytest
from fastapi import HTTPException

from src.server.api import config, config_validation


def test_validate_acp_port_accepts_integer_range_only():
    """SPEC-020 AC-5：1-65535 的整数通过，其余 400 且文案不变。"""
    assert config_validation.validate_acp_port(1) == 1
    assert config_validation.validate_acp_port(65535) == 65535

    for bad in (0, 65536, -1, "8000", None, 3.5):
        with pytest.raises(HTTPException) as exc:
            config_validation.validate_acp_port(bad)
        assert exc.value.status_code == 400
        assert exc.value.detail == "端口必须是 1-65536 的整数"


def test_config_keeps_validate_acp_port_alias():
    """SPEC-020 AC-5：旧入口 config._validate_acp_port 行为不变。"""
    assert config._validate_acp_port(8000) == 8000
    with pytest.raises(HTTPException) as exc:
        config._validate_acp_port(70000)
    assert exc.value.detail == "端口必须是 1-65536 的整数"


def test_validate_data_root_normalizes_absolute_path(tmp_path):
    """SPEC-020 AC-5：合法绝对路径返回 normpath 后的值。"""
    assert config_validation.validate_data_root(str(tmp_path)) == os.path.normpath(
        str(tmp_path)
    )
    assert config._validate_data_root(str(tmp_path)) == os.path.normpath(str(tmp_path))


@pytest.mark.parametrize("bad", ["", "   ", "relative/path", None, 123])
def test_validate_data_root_rejects_empty_and_relative(bad):
    """SPEC-020 AC-5：空值、非字符串与相对路径均 400。"""
    with pytest.raises(HTTPException) as exc:
        config_validation.validate_data_root(bad)
    assert exc.value.status_code == 400
    expected = (
        "数据目录不能为空"
        if bad is None or not isinstance(bad, str) or not bad.strip()
        else "数据目录必须是绝对路径，如 D:\\purrcat_data"
    )
    assert exc.value.detail == expected


def test_validate_data_root_rejects_drive_root(tmp_path):
    """SPEC-020 AC-5：磁盘根目录（如 D:\\）被拒绝。"""
    drive, _ = os.path.splitdrive(str(tmp_path))
    if not drive:
        pytest.skip("当前平台无盘符概念")
    with pytest.raises(HTTPException) as exc:
        config_validation.validate_data_root(drive + os.sep)
    assert exc.value.status_code == 400
    assert exc.value.detail == "不能直接选择磁盘根目录，请选择盘下的一个子目录"


def test_validate_markdown_filename_whitelist():
    """SPEC-020 AC-5：只允许 SOUL / GOAL，其余 400 Invalid filename。"""
    for name in ("SOUL", "GOAL"):
        assert config_validation.validate_markdown_filename(name) == name
    for bad in ("soul", "GOAL.md", "", "../SOUL"):
        with pytest.raises(HTTPException) as exc:
            config_validation.validate_markdown_filename(bad)
        assert exc.value.status_code == 400
        assert exc.value.detail == "Invalid filename"


def test_load_json_data_missing_and_broken_use_default(tmp_path):
    """SPEC-020 AC-5：文件缺失或损坏时返回调用方默认值。"""
    assert config_validation.load_json_data(
        str(tmp_path / "missing.json"), {"jobs": []}
    ) == {"jobs": []}

    broken = tmp_path / "broken.json"
    broken.write_text("{", encoding="utf-8")
    assert config_validation.load_json_data(str(broken), {"jobs": []}) == {"jobs": []}

    valid = tmp_path / "valid.json"
    valid.write_text(json.dumps([1, 2]), encoding="utf-8")
    assert config_validation.load_json_data(str(valid), {}) == [1, 2]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("  ghcr.m.daocloud.io/  ", "ghcr.m.daocloud.io"),
        ("docker.io", "docker.io"),
        (None, ""),
        ("", ""),
    ],
)
def test_normalize_sandbox_registry_strips_and_trims_slash(raw, expected):
    """SPEC-020 AC-5：registry 去掉首尾空白与末尾斜杠，空值归一化空串。"""
    assert config_validation.normalize_sandbox_registry(raw) == expected
