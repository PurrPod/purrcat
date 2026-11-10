"""工具市场归档层：远程下载、zip 解包与解压目标计算。

网络与磁盘操作集中在这里；解压路径、SKILL.md 校验等判断抽成纯函数，
便于用 tmp_path 直接测试。
"""

from __future__ import annotations

import io
import json
import os
import re
import shutil
import urllib.request
import zipfile

from fastapi import HTTPException

from src.server.api.tools_registry import (
    REMOTE_REQUEST_TIMEOUT,
    default_branch_candidates,
)
from src.server.api.tools_validation import parse_skill_github_url
from src.utils.config import MCP_SOURCE_DIR, SKILL_DIR

OFFICIAL_MCP_REPO_PATTERN = r"https?://github\.com/PurrPod/mcps"
OFFICIAL_MCP_ZIP_URL = "https://github.com/PurrPod/mcps/archive/refs/heads/main.zip"


def http_get_json(url: str, timeout: int = REMOTE_REQUEST_TIMEOUT):
    """同步 GET 一个远程 URL 并解析 JSON，带超时防卡死。"""
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "purrcat-market/1.0",
            "Accept": "application/json,text/plain,*/*",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("utf-8", errors="replace")
    return json.loads(text)


def http_download(url: str, timeout: int = REMOTE_REQUEST_TIMEOUT) -> bytes:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "purrcat-market/1.0",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def fetch_repo_zip(owner: str, repo: str, branch: str) -> bytes:
    """下载仓库 zip 字节流；branch 为空（裸仓库链接）时自动探测默认分支。"""
    default_branch = ""
    if not branch:
        try:
            info = http_get_json(
                f"https://api.github.com/repos/{owner}/{repo}", timeout=10
            )
            default_branch = (
                info.get("default_branch") if isinstance(info, dict) else ""
            )
        except Exception:
            default_branch = ""

    last_err = None
    for b in default_branch_candidates(branch, default_branch):
        zip_url = f"https://github.com/{owner}/{repo}/archive/refs/heads/{b}.zip"
        try:
            return http_download(zip_url)
        except Exception as e:
            last_err = e
    raise last_err or ValueError(f"仓库 {owner}/{repo} 下载失败")


def skill_name_from_path(repo: str, path: str) -> str:
    """仓库根目录即 skill 时用仓库名，否则用子目录名。"""
    return os.path.basename(path) if path else repo


def archive_root_folder(names: list) -> str:
    """zip 首项的第一段即仓库解压根目录。"""
    return names[0].split("/")[0]


def skill_archive_prefix(root_folder: str, path: str) -> str:
    """skill 子目录在 zip 内的前缀，统一以 / 结尾。"""
    return f"{root_folder}/{path}".rstrip("/") + "/"


def has_skill_md(infos, prefix: str) -> bool:
    """目标前缀下是否存在 SKILL.md（忽略大小写与目录项）。"""
    target = (prefix + "SKILL.md").lower()
    return any(
        info.filename.rstrip("/").lower() == target
        for info in infos
        if not info.is_dir()
    )


def extract_skill_from_zip(zip_data: bytes, repo: str, path: str) -> str:
    """从仓库 zip 字节流中解压单个 skill 子目录到 SKILL_DIR，返回 skill 名。

    仅当目标目录内存在 SKILL.md 时才视为合法 Skill，否则直接报错。
    """
    skill_name = skill_name_from_path(repo, path)
    dest_dir = os.path.join(SKILL_DIR, skill_name)

    with zipfile.ZipFile(io.BytesIO(zip_data)) as z:
        root_folder = archive_root_folder(z.namelist())
        target_prefix = skill_archive_prefix(root_folder, path)

        # 目录校验：目标文件夹必须包含 SKILL.md，否则不是合法 Skill
        if not has_skill_md(z.infolist(), target_prefix):
            raise HTTPException(
                status_code=400,
                detail=f"目录 '{path or repo}' 下未找到 SKILL.md，无法作为 Skill 安装",
            )

        # 校验通过后再覆盖式重装：先清掉旧目录，保证与仓库当前版本一致
        if os.path.isdir(dest_dir):
            shutil.rmtree(dest_dir)

        extracted_count = 0
        for file_info in z.infolist():
            if file_info.filename.startswith(target_prefix):
                relative_path = file_info.filename[len(target_prefix) :]
                if not relative_path:
                    continue

                local_path = os.path.join(dest_dir, relative_path)
                if file_info.is_dir():
                    os.makedirs(local_path, exist_ok=True)
                else:
                    os.makedirs(os.path.dirname(local_path), exist_ok=True)
                    with open(local_path, "wb") as f:
                        f.write(z.read(file_info.filename))
                extracted_count += 1

        if extracted_count == 0:
            raise HTTPException(status_code=404, detail=f"仓库中找不到文件夹 '{path}'")
    return skill_name


def download_skill_from_github(url: str) -> str:
    """根据 GitHub URL 下载第三方 Skill 到本地 SKILL_DIR，返回 skill 名。"""
    owner, repo, branch, path = parse_skill_github_url(url)
    zip_data = fetch_repo_zip(owner, repo, branch)
    return extract_skill_from_zip(zip_data, repo, path)


def official_mcp_prefixes(root_folder: str, name: str) -> tuple[str, str]:
    """官方 mcps 仓库内可能的两级目录前缀。"""
    return (f"{root_folder}/{name}/", f"{root_folder}/mcps/{name}/")


def download_official_mcp_source(repo: str, server_names: list) -> str:
    """官方 MCP：从 PurrPod/mcps 仓库下载对应子文件夹源码到 ~/.purrcat/mcps/。"""
    if not re.match(OFFICIAL_MCP_REPO_PATTERN, repo):
        return ""

    with urllib.request.urlopen(OFFICIAL_MCP_ZIP_URL) as response:
        zip_data = response.read()

    downloaded = []
    with zipfile.ZipFile(io.BytesIO(zip_data)) as z:
        root_folder = archive_root_folder(z.namelist())

        for name in server_names:
            # 兼容仓库内不同目录层级：<root>/<name>/ 或 <root>/mcps/<name>/
            target_prefix = None
            for candidate in official_mcp_prefixes(root_folder, name):
                if any(f.filename.startswith(candidate) for f in z.infolist()):
                    target_prefix = candidate
                    break
            if not target_prefix:
                continue

            dest_dir = os.path.join(MCP_SOURCE_DIR, name)
            for file_info in z.infolist():
                if file_info.filename.startswith(target_prefix):
                    relative_path = file_info.filename[len(target_prefix) :]
                    if not relative_path:
                        continue
                    local_path = os.path.join(dest_dir, relative_path)
                    if file_info.is_dir():
                        os.makedirs(local_path, exist_ok=True)
                    else:
                        os.makedirs(os.path.dirname(local_path), exist_ok=True)
                        with open(local_path, "wb") as f:
                            f.write(z.read(file_info.filename))
            downloaded.append(name)

    return ",".join(downloaded)
