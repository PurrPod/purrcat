"""部署项的平台命令构造与检测结果判定（SPEC-015）。"""

from __future__ import annotations

from src.utils import deploy_installers as installers


def test_uv_install_command_per_platform():
    assert installers.uv_install_command("win32") == [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        "irm https://astral.sh/uv/install.ps1 | iex",
    ]
    assert installers.uv_install_command("linux") == [
        "sh",
        "-c",
        "curl -LsSf https://astral.sh/uv/install.sh | sh",
    ]


def test_node_install_commands_keep_winget_and_brew_flags():
    assert installers.node_winget_command("winget") == [
        "winget",
        "install",
        "--id",
        "OpenJS.NodeJS.LTS",
        "-e",
        "--accept-source-agreements",
        "--accept-package-agreements",
    ]
    assert installers.node_brew_command("brew") == ["brew", "install", "node"]


def test_node_linux_candidates_are_non_interactive():
    candidates = installers.node_linux_candidates()

    assert [name for name, _ in candidates] == ["apt-get", "dnf", "yum", "pacman"]
    for name, cmd in candidates:
        assert cmd[:3] == ["sudo", "-n", name]
        assert "nodejs" in cmd and "npm" in cmd


def test_docker_desktop_install_commands():
    assert installers.docker_desktop_winget_command("winget") == [
        "winget",
        "install",
        "--id",
        "Docker.DockerDesktop",
        "-e",
        "--accept-source-agreements",
        "--accept-package-agreements",
    ]
    assert installers.docker_desktop_brew_command("brew") == [
        "brew",
        "install",
        "--cask",
        "docker",
    ]
    assert installers.docker_linux_install_command() == [
        "sh",
        "-c",
        "curl -fsSL https://get.docker.com | sudo -n sh",
    ]
