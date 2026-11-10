"""跨工具共享纯函数：MCP 配置、混合检索与请求文案（SPEC-016 AC-9）。"""

from __future__ import annotations

import base64
import math

import numpy as np

from src.tool.callmcp import _shared as mcp_shared
from src.tool.request import _shared as request_shared
from src.tool.search import _shared as search_shared
from src.tool.task import _shared as task_shared


def test_config_fingerprint_tracks_command_args_and_env():
    """SPEC-016 AC-9：command/args/env 任一变化都会改变指纹。"""
    base = {"command": "npx", "args": ["-y", "server"], "env": {"A": "1"}}

    assert mcp_shared.config_fingerprint(base) == mcp_shared.config_fingerprint(
        dict(base)
    )
    assert mcp_shared.config_fingerprint(base) != mcp_shared.config_fingerprint(
        {**base, "command": "node"}
    )
    assert mcp_shared.config_fingerprint(base) != mcp_shared.config_fingerprint(
        {**base, "args": ["other"]}
    )
    assert mcp_shared.config_fingerprint(base) != mcp_shared.config_fingerprint(
        {**base, "env": {"A": "2"}}
    )


def test_build_safe_env_filters_none_and_parent_python_vars():
    """SPEC-016 AC-9：None 值被跳过、值转字符串，父进程 Python 变量被剥离。"""
    base = {"PATH": "/bin", "PYTHONHOME": "/venv", "PYTHONPATH": "/src"}
    custom = {"TOKEN": 123, "EMPTY": None, "VIRTUAL_ENV": "/v"}

    env = mcp_shared.build_safe_env(custom, base)

    assert env == {"PATH": "/bin", "TOKEN": "123"}


def test_decode_image_content_strips_data_url_and_normalizes_ext():
    """SPEC-016 AC-9：data URL 前缀被剥离，jpeg 归一化为 jpg。"""

    class Content:
        mimeType = "image/jpeg"
        data = "data:image/jpeg;base64," + base64.b64encode(b"img").decode()

    raw, ext = mcp_shared.decode_image_content(Content())

    assert raw == b"img"
    assert ext == "jpg"


def test_hybrid_scores_preserve_negative_bm25_difference():
    """SPEC-016 AC-9：Skill 截断 BM25 负分，MCP 保持原逻辑。"""
    dense = np.array([0.5, 0.4])
    bm25 = np.array([-1.0, 0.0])

    unclamped = search_shared.hybrid_scores(dense, bm25, clamp_negative=False)
    clamped = search_shared.hybrid_scores(dense, bm25, clamp_negative=True)

    assert math.isinf(unclamped[0]) and unclamped[0] < 0
    assert clamped[0] == 0.5
    assert clamped[1] == 0.4


def test_evaluate_rank_reports_score_rank_and_threshold():
    """SPEC-016 AC-9：名次判定使用 TopK 顺序与阈值。"""
    scores = np.array([0.9, 0.5, 0.2])
    indices = np.array([0, 1, 2])

    assert search_shared.evaluate_rank(scores, indices, 1, 0.3) == (True, 2, 0.5)
    assert search_shared.evaluate_rank(scores, indices, 1, 0.6) == (False, -1, 0.5)
    assert search_shared.evaluate_rank(scores, indices, -1, 0.3) == (False, -1, 0.0)


def test_split_merge_target_trims_both_parts():
    """SPEC-016 AC-9：合并目标按 'uuid/名字' 拆分并去空白。"""
    assert request_shared.split_merge_target(" uuid / skill ") == ("uuid", "skill")
    assert request_shared.split_merge_target("") == ("", "")


def test_rejection_feedback_matches_request_type():
    """SPEC-016 AC-9：不同请求类型的拒绝文案保持原有措辞。"""
    assert "测试申请" in request_shared.format_rejection_feedback(
        "skill_test", "用例不足"
    )
    assert "协议体检申请" in request_shared.format_rejection_feedback(
        "sensor_test", "缺少探针"
    )
    merge_text = request_shared.format_rejection_feedback("graph_merge", "非法节点")
    assert "代码合并请求" in merge_text
    assert "【拒绝理由】: 非法节点" in merge_text
    assert request_shared.format_rejection_feedback("file_read", "x") == "x"


def test_decision_callback_marks_auto_permission_only_for_plain_types():
    """SPEC-016 AC-9：普通授权通过时追加自动下发提示，合并类不追加。"""
    granted = request_shared.build_decision_callback(
        "r1", "path", True, "file_write", "ok"
    )
    merged = request_shared.build_decision_callback(
        "r2", "u/n", True, "graph_merge", "ok"
    )

    assert "【同意并已生效】" in granted
    assert "自动下发权限" in granted
    assert "自动下发权限" not in merged


def test_task_name_rejects_path_separators_and_dots():
    """SPEC-016 AC-9：任务名禁止路径分隔符与小数点，正常名称放行。"""
    assert task_shared.validate_task_name("周报") is None
    assert task_shared.validate_task_name("a/b") is not None
    assert task_shared.validate_task_name("a.b") is not None


def test_task_param_validation_reports_missing_and_extra():
    """SPEC-016 AC-9：缺失必填与未知参数分别成段，空错误返回空串。"""
    schema = {
        "topic": {"required": True, "type": "string", "description": "主题"},
        "style": {"required": False},
    }

    missing = task_shared.collect_missing_required(schema, {"style": "短"})
    extra = task_shared.collect_extra_keys(schema, {"topic": "x", "unknown": 1})
    text = task_shared.build_param_error_text(missing, extra, "report")

    assert missing == [{"name": "topic", "type": "string", "description": "主题"}]
    assert extra == ["unknown"]
    assert "缺少必填参数" in text
    assert "'unknown'" in text
    assert "action='list_graphs'" in text
    assert task_shared.build_param_error_text([], [], "report") == ""
