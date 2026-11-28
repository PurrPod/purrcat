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
    if os.name == "nt":
        # 反斜杠是 Windows 原生分隔符；POSIX 上它只是普通字符，不做归一化
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


def test_build_import_changes_restores_image_metadata():
    """压平镜像时必须回填 CMD/ENTRYPOINT/ENV/WORKDIR/USER，避免容器行为变化。"""
    from src.tool.bash.docker_env import build_import_changes

    changes = build_import_changes(
        {
            "Cmd": ["sleep", "infinity"],
            "Entrypoint": ["/entry.sh"],
            "Env": ["PATH=/usr/bin", "LANG=C.UTF-8"],
            "WorkingDir": "/agent_vm",
            "User": "root",
        }
    )

    assert "--change" in changes
    assert 'CMD ["sleep", "infinity"]' in changes
    assert 'ENTRYPOINT ["/entry.sh"]' in changes
    assert "ENV PATH=/usr/bin" in changes
    assert "ENV LANG=C.UTF-8" in changes
    assert "WORKDIR /agent_vm" in changes
    assert "USER root" in changes


def test_build_import_changes_defaults_to_sleep_command():
    """基础镜像没有 CMD 时，回填默认的 sleep infinity 以维持沙盒常驻。"""
    from src.tool.bash.docker_env import build_import_changes

    assert 'CMD ["sleep", "infinity"]' in build_import_changes({})


def test_build_container_path_prepends_env_dirs_and_keeps_image_path():
    """容器启动环境里的 PATH 应包含持久工具目录，并保留镜像自带项。"""
    from src.tool.bash.docker_env import build_container_path

    path = build_container_path(
        "/agent_vm", ["PATH=/opt/bin:/usr/local/bin:/usr/bin", "LANG=C.UTF-8"]
    )

    assert (
        path
        == "/agent_vm/.env/bin:/agent_vm/.env/npm/bin:/opt/bin:/usr/local/bin:/usr/bin"
    )
    assert build_container_path("/agent_vm").startswith("/agent_vm/.env/bin:")
    # 快照镜像已带同一前缀时不重复叠加
    once = "/agent_vm/.env/bin:/agent_vm/.env/npm/bin:/usr/bin"
    assert build_container_path("/agent_vm", [f"PATH={once}"]) == once


def test_is_docker_conn_error_detects_closed_pipe():
    """Docker 引擎重启后旧命名管道会以 WinError 232 / broken pipe 报错，需识别后重连。"""
    from src.tool.bash.docker_env import _is_docker_conn_error

    class _WinError(Exception):
        winerror = 232

    assert _is_docker_conn_error(_WinError("WriteFile"))
    assert _is_docker_conn_error(BrokenPipeError("broken"))
    assert _is_docker_conn_error(OSError(232, "WriteFile", "管道正在被关闭。"))
    assert _is_docker_conn_error(OSError(232, "WriteFile", "The pipe is being closed."))
    assert not _is_docker_conn_error(RuntimeError("挂载源不存在"))


def test_start_recovers_from_dead_docker_pipe(monkeypatch):
    """启动时遇到管道断开应重连并重试一次，而不是把错误抛给前端。"""
    from src.tool.bash import docker_env

    mgr = object.__new__(docker_env.DockerManager)
    mgr._started = False
    mgr.container = None
    calls = {"start": 0, "reset": 0}

    def flaky():
        calls["start"] += 1
        if calls["start"] == 1:
            raise OSError(232, "WriteFile", "管道正在被关闭。")

    mgr._start_locked = flaky
    mgr._reset_client = lambda: calls.__setitem__("reset", calls["reset"] + 1)
    monkeypatch.setattr(docker_env.time, "sleep", lambda *_: None)

    mgr._start_with_recovery()

    assert calls == {"start": 2, "reset": 1}
