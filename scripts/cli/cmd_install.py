"""PurrCat install command - Extension manager for skills, nodes, graphs, and MCPs"""

import io
import json
import os
import re
import urllib.request
import zipfile


def _get_project_root():
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _download_and_extract_subfolder(zip_url, subfolder_path, dest_dir):
    """Download ZIP and extract only the specified subfolder in memory."""
    print(f"[*] Downloading from {zip_url} ...")
    try:
        req = urllib.request.Request(zip_url, headers={"User-Agent": "PurrCat-CLI/1.0"})
        response = urllib.request.urlopen(req)
        zip_data = response.read()

        with zipfile.ZipFile(io.BytesIO(zip_data)) as z:
            root_folder = z.namelist()[0].split("/")[0]
            target_prefix = f"{root_folder}/{subfolder_path}".rstrip("/") + "/"

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
                print(
                    f"X Error: Could not find folder '{subfolder_path}' in the repository."
                )
                return False

        return True
    except Exception as e:
        print(f"X Download/Extract failed: {e}")
        return False


def _parse_github_url(url):
    """Parse GitHub URL to extract owner, repo, branch and target path."""
    match = re.match(r"https?://github\.com/([^/]+)/([^/]+)/tree/([^/]+)/(.*)", url)
    if match:
        return {
            "owner": match.group(1),
            "repo": match.group(2),
            "branch": match.group(3),
            "path": match.group(4),
        }
    return None


def run_install(ext_type, source):
    """Execute install logic (支持 MCP, Graph自动依赖解析, Skill, Node)"""
    project_root = _get_project_root()

    print(f"\nInstalling {ext_type}...")
    print("==========================================")

    # ---------------------------------------------------------
    # 1. MCP 安装逻辑：将传入的 JSON string 写入全局 mcp_config.json
    # ---------------------------------------------------------
    if ext_type == "mcp":
        mcp_config_path = os.path.join(project_root, ".purrcat", "mcp_config.json")
        try:
            new_mcp = json.loads(source)
            # 加载已有的 mcp_config.json
            if os.path.exists(mcp_config_path):
                with open(mcp_config_path, "r", encoding="utf-8") as f:
                    current_config = json.load(f)
            else:
                current_config = {"mcpServers": {}}

            if "mcpServers" not in current_config:
                current_config["mcpServers"] = {}

            # 合并新增的 MCP Server 配置
            for server_name, server_config in new_mcp.items():
                current_config["mcpServers"][server_name] = server_config
                print(f"  -> Added/Updated MCP server: {server_name}")

            os.makedirs(os.path.dirname(mcp_config_path), exist_ok=True)
            with open(mcp_config_path, "w", encoding="utf-8") as f:
                json.dump(current_config, f, indent=2, ensure_ascii=False)
            print("[+] Successfully installed MCP configurations.")
        except json.JSONDecodeError as e:
            print(f"X Error: Invalid JSON string for MCP configuration. {e}")
        except Exception as e:
            print(f"X Failed to install MCP: {e}")

    # ---------------------------------------------------------
    # 2. Graph 安装逻辑：从 PurrPod/graphpod 拉取并解析依赖
    # ---------------------------------------------------------
    elif ext_type == "graph":
        graph_name = source
        if not graph_name.endswith(".json"):
            graph_filename = f"{graph_name}.json"
        else:
            graph_filename = graph_name
            graph_name = graph_name[:-5]

        # 直接从 raw.githubusercontent.com 拉取单文件，速度最快最稳定
        raw_url = (
            f"https://raw.githubusercontent.com/PurrPod/graphpod/main/{graph_filename}"
        )
        dest_dir = os.path.join(project_root, "src", "harness", "graph")
        os.makedirs(dest_dir, exist_ok=True)
        dest_path = os.path.join(dest_dir, graph_filename)

        print(f"[*] Fetching graph '{graph_name}' from PurrPod/graphpod...")
        try:
            req = urllib.request.Request(
                raw_url, headers={"User-Agent": "PurrCat-CLI/1.0"}
            )
            response = urllib.request.urlopen(req)
            graph_data = response.read().decode("utf-8")

            # 落盘保存图 json
            with open(dest_path, "w", encoding="utf-8") as f:
                f.write(graph_data)
            print(f"[+] Successfully downloaded graph to {dest_path}")

            # ======= 解析依赖并自动安装 =======
            try:
                graph_json = json.loads(graph_data)
                deps = graph_json.get("dependencies", {})
                skills = deps.get("skills", [])
                mcps = deps.get("mcps", {})

                if skills:
                    print(
                        f"\n[*] Graph '{graph_name}' requires {len(skills)} skill(s). Installing dependencies..."
                    )
                    for skill_url in skills:
                        # 递归调用安装 Skill
                        run_install("skill", skill_url)

                if mcps:
                    print(
                        f"\n[*] Graph '{graph_name}' requires MCP server(s). Installing dependencies..."
                    )
                    # 递归调用安装 MCP (转为JSON字符串传入)
                    run_install("mcp", json.dumps(mcps))

            except json.JSONDecodeError:
                print(
                    "X Error: Downloaded graph file is not valid JSON. Skipping dependency check."
                )

        except urllib.error.HTTPError as e:
            if e.code == 404:
                print(
                    f"X Error: Graph '{graph_filename}' not found in PurrPod/graphpod repository."
                )
            else:
                print(f"X HTTP Error fetching graph: {e}")
        except Exception as e:
            print(f"X Failed to download graph: {e}")

    # ---------------------------------------------------------
    # 3. Node 安装逻辑：沿用官方仓库
    # ---------------------------------------------------------
    elif ext_type == "node":
        OFFICIAL_REPO_ZIP = (
            "https://github.com/PurrPod/node/archive/refs/heads/main.zip"
        )
        dest_dir = os.path.join(
            project_root, "src", "harness", "node", "extensions", source
        )
        subfolder_path = f"node/{source}"

        print(f"[*] Fetching official node '{source}' from PurrPod/node...")
        if _download_and_extract_subfolder(OFFICIAL_REPO_ZIP, subfolder_path, dest_dir):
            print(f"[+] Successfully installed node '{source}' to {dest_dir}")

    # ---------------------------------------------------------
    # 4. Skill 安装逻辑：支持第三方 GitHub 链接
    # ---------------------------------------------------------
    elif ext_type == "skill":
        if source.startswith("http"):
            parsed = _parse_github_url(source)
            if not parsed:
                print("X Error: Invalid GitHub URL format.")
                print(
                    "  Expected: https://github.com/owner/repo/tree/branch/path/to/skill"
                )
                return

            skill_name = os.path.basename(parsed["path"].rstrip("/"))
            dest_dir = os.path.join(project_root, "skills", skill_name)

            zip_url = f"https://github.com/{parsed['owner']}/{parsed['repo']}/archive/refs/heads/{parsed['branch']}.zip"

            print(
                f"[*] Fetching skill '{skill_name}' from {parsed['owner']}/{parsed['repo']}"
            )
            if _download_and_extract_subfolder(zip_url, parsed["path"], dest_dir):
                print(
                    f"[+] Successfully installed skill '{skill_name}' to skills/{skill_name}"
                )
        else:
            print("X Error: Currently, skill installation requires a full GitHub URL.")
            print(
                "  Example: purrcat install skill https://github.com/user/repo/tree/main/path/to/skill"
            )

    else:
        print(f"X Unknown extension type: {ext_type}")
        print("  Supported types: skill, node, graph, mcp")
