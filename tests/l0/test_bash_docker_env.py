"""Bash 沙盒的命令与参数构造（SPEC-016 AC-8）。"""

from __future__ import annotations

import os

from src.tool.bash import _shared


def test_build_exec_command_uses_i_flag_on_windows():
    """SPEC-016 AC-8：Windows 下 docker exec 使用 -i（无 TTY）。"""
    assert (
        _shared.build_exec_command("C:/docker.exe", "agent_computer", platform="win32")
        == "C:/docker.exe exec -i agent_computer /bin/bash"
    )


def test_build_exec_command_uses_it_flag_on_posix():
    """SPEC-016 AC-8：非 Windows 平台保留 -it。"""
    assert (
        _shared.build_exec_command("/usr/bin/docker", "box", platform="linux")
        == "/usr/bin/docker exec -it box /bin/bash"
    )


def test_build_shell_payload_wraps_and_redirects_stdin():
    """SPEC-016 AC-8：命令被代码块包裹并强制 stdin 重定向，末尾打印标记。"""
    payload = _shared.build_shell_payload("echo hi", "__CMD_DONE_x__")

    assert payload == (
        '{\necho hi\n} < /dev/null\necho -e "\\n__CMD_DONE_x__$?|$(pwd)"'
    )


def test_strip_command_echo_removes_only_echoed_command():
    """SPEC-016 AC-8：输出清洗只移除与命令完全一致的回显行。"""
    output = "echo hi\nhello\n echo hi \nworld"

    assert _shared.strip_command_echo(output, "echo hi") == "hello\nworld"


def test_clean_ansi_removes_escape_sequences_and_carriage_returns():
    """SPEC-016 AC-8：ANSI 转义与 \\r 被清除。"""
    assert _shared.clean_ansi("\x1b[31mred\x1b[0m\r\nok") == "red\nok"


def test_container_env_points_caches_to_tmpfs():
    """SPEC-016 AC-8：缓存目录统一指向容器内 /tmp，避免写大可写层。"""
    env = _shared.container_env()

    assert env["XDG_CACHE_HOME"] == "/tmp/.cache"
    assert env["PIP_CACHE_DIR"] == "/tmp/.cache/pip"
    assert env["UV_CACHE_DIR"] == "/tmp/.cache/uv"
    assert env["npm_config_cache"] == "/tmp/.cache/npm"


def test_normalize_mount_path_handles_drive_style_and_case():
    """SPEC-016 AC-8：D:/x、/d/x 与反斜杠形式归一化后一致。"""
    expected = os.path.normpath("d:" + os.sep + "work").lower()

    assert _shared.normalize_mount_path("D:/work") == expected
    assert _shared.normalize_mount_path("/d/work") == expected
    assert _shared.normalize_mount_path("d:\\WORK") == expected


def test_exit_hook_skips_docker_when_no_sandbox_was_created(monkeypatch):
    """从未创建沙盒的进程（测试 / 纯 API）退出时不应触碰 Docker。"""
    from src.tool.bash import docker_env

    called = []
    monkeypatch.setattr(docker_env, "_docker_manager_instance", None)
    monkeypatch.setattr(docker_env.docker, "from_env", lambda **kw: called.append(kw))

    docker_env._stop_sandbox_on_exit()

    assert called == []


def test_exit_hook_ignores_missing_container(monkeypatch, capsys):
    """容器已被删除时静默返回，不打印误导性的失败日志。"""
    from src.tool.bash import docker_env

    class _Containers:
        def get(self, name):
            raise docker_env.NotFound("No such container")

    class _Client:
        containers = _Containers()

    monkeypatch.setattr(docker_env, "_docker_manager_instance", object())
    monkeypatch.setattr(docker_env.docker, "from_env", lambda **kw: _Client())

    docker_env._stop_sandbox_on_exit()

    assert "失败" not in capsys.readouterr().out
