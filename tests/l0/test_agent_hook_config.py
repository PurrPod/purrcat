"""范式配置加载、默认回退与动态别名注册（SPEC-018）。"""

from __future__ import annotations

from src.agent import hook_handler as hook_mod
from src.agent.hook_handler import HookHandler

YAML_TEXT = """\
loop_end_max_retry: 7
hooks:
  on_loop_start:
    - injection:
        content: hi
"""


def _handler(hooks: dict | None = None) -> HookHandler:
    return HookHandler(config_dict={"hooks": hooks or {}})


def test_inline_config_dict_uses_hooks_without_loading_file():
    handler = HookHandler(config_dict={"hooks": {"on_loop_end": []}})

    assert handler.paradigm_path == "<inline>"
    assert handler.config == {"hooks": {"on_loop_end": []}}
    assert handler.hooks == {"on_loop_end": []}


def test_load_config_reads_yaml_config_and_hooks(tmp_path):
    path = tmp_path / "PARADIGM.yaml"
    path.write_text(YAML_TEXT, encoding="utf-8")
    handler = _handler()

    handler.load_config(str(path))

    assert handler.paradigm_path == str(path)
    assert handler.config["loop_end_max_retry"] == 7
    assert handler.hooks["on_loop_start"][0]["injection"]["content"] == "hi"


def test_load_config_missing_file_resets_config_and_hooks(tmp_path):
    handler = _handler({"on_loop_start": [{"injection": {"content": "旧"}}]})

    handler.load_config(str(tmp_path / "missing.yaml"))

    assert handler.config == {}
    assert handler.hooks == {}


def test_get_state_and_load_state_restore_paradigm_path(tmp_path):
    path = tmp_path / "PARADIGM.yaml"
    path.write_text(YAML_TEXT, encoding="utf-8")
    source = _handler()
    source.load_config(str(path))
    target = _handler()

    target.load_state(source.get_state())

    assert target.paradigm_path == str(path)
    assert target.hooks["on_loop_start"][0]["injection"]["content"] == "hi"


def test_default_paradigm_path_prefers_existing_user_file(tmp_path, monkeypatch):
    user_path = tmp_path / "PARADIGM.yaml"
    user_path.write_text("hooks: {}\n", encoding="utf-8")
    monkeypatch.setattr(hook_mod, "USER_PARADIGM_PATH", str(user_path))
    monkeypatch.setattr(hook_mod, "PARADIGMS_DIR", str(tmp_path))
    monkeypatch.setattr(
        hook_mod, "DEFAULT_PARADIGM_PATH", str(tmp_path / "fallback.yaml")
    )

    assert hook_mod._default_paradigm_path() == str(user_path)


def test_default_paradigm_path_writes_template_when_missing(tmp_path, monkeypatch):
    user_path = tmp_path / "config" / "PARADIGM.yaml"
    monkeypatch.setattr(hook_mod, "USER_PARADIGM_PATH", str(user_path))
    monkeypatch.setattr(hook_mod, "PARADIGMS_DIR", str(user_path.parent))
    monkeypatch.setattr(
        hook_mod, "DEFAULT_PARADIGM_PATH", str(tmp_path / "fallback.yaml")
    )
    monkeypatch.setattr("src.utils.initial.DEFAULT_PARADIGM_YAML", "hooks: {}\n")

    assert hook_mod._default_paradigm_path() == str(user_path)
    assert user_path.read_text(encoding="utf-8") == "hooks: {}\n"


def test_default_paradigm_path_falls_back_when_template_cannot_be_written(
    tmp_path, monkeypatch
):
    blocked = tmp_path / "blocked"
    blocked.write_text("not a directory", encoding="utf-8")
    monkeypatch.setattr(hook_mod, "PARADIGMS_DIR", str(blocked))
    monkeypatch.setattr(hook_mod, "USER_PARADIGM_PATH", str(blocked / "PARADIGM.yaml"))
    fallback = tmp_path / "fallback.yaml"
    monkeypatch.setattr(hook_mod, "DEFAULT_PARADIGM_PATH", str(fallback))

    assert hook_mod._default_paradigm_path() == str(fallback)


def test_add_alias_registers_content_and_host_path_prefix(tmp_path):
    handler = _handler(
        {"on_loop_start": [{"injection": {"content": "沙盒：@TASKSPACE"}}]}
    )

    handler.add_alias("@TASKSPACE", host_path=str(tmp_path), content="/agent_vm/tasks")

    assert handler.extra_path_aliases["@TASKSPACE"] == str(tmp_path)
    assert handler.extra_content_aliases["@TASKSPACE"] == "/agent_vm/tasks"
    assert handler.execute("on_loop_start", epoch=0)[0]["inject_prompt"] == (
        "沙盒：/agent_vm/tasks"
    )
    assert handler._resolve_path("@TASKSPACE/demo.txt") == str(tmp_path / "demo.txt")


def test_unknown_alias_stays_literal_until_registered():
    hooks = {"on_loop_start": [{"injection": {"content": "@EXTRA"}}]}
    handler = _handler(hooks)

    assert handler.execute("on_loop_start", epoch=0)[0]["inject_prompt"] == "@EXTRA"

    handler.add_alias("@EXTRA", content="已注册")
    assert handler.execute("on_loop_start", epoch=0)[0]["inject_prompt"] == "已注册"


def test_execute_respects_delay_and_interval():
    handler = _handler(
        {
            "on_loop_start": [
                {"injection": {"content": "仅第2轮", "delay": 2}},
                {"injection": {"content": "每2轮", "interval": 2}},
            ]
        }
    )

    assert handler.execute("on_loop_start", epoch=1) == []
    assert [r["inject_prompt"] for r in handler.execute("on_loop_start", epoch=2)] == [
        "仅第2轮",
        "每2轮",
    ]
    assert [r["inject_prompt"] for r in handler.execute("on_loop_start", epoch=4)] == [
        "每2轮"
    ]
