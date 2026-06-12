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
    # 1. MCP 安装逻辑：支持查表 (Registry) 或直接传入 JSON string
    # ---------------------------------------------------------
    if ext_type == "mcp":
        mcp_config_path = os.path.join(project_root, ".purrcat", "mcp_config.json")
        new_mcp_configs = {}

        # 场景 A: 传入的是原生 JSON 字符串 (向下兼容)
        if source.strip().startswith("{"):
            try:
                new_mcp_configs = json.loads(source)
            except json.JSONDecodeError as e:
                print(f"X Error: Invalid JSON string for MCP configuration. {e}")
                return
        # 场景 B: 传入的是短名，需要去 registry 查表
        else:
            registry_url = (
                "https://raw.githubusercontent.com/PurrPod/mcps/main/registry.json"
            )
            print(f"[*] Querying MCP registry for '{source}'...")
            try:
                req = urllib.request.Request(
                    registry_url, headers={"User-Agent": "PurrCat-CLI/1.0"}
                )
                response = urllib.request.urlopen(req)
                registry_data = json.loads(response.read().decode("utf-8"))

                mcps_dict = registry_data.get("mcps", {})
                if source not in mcps_dict:
                    print(f"X Error: MCP '{source}' not found in official registry.")
                    print(f"  Available MCPs: {', '.join(mcps_dict.keys())}")
                    return

                # 提取注册表中的 config 块作为安装内容
                new_mcp_configs[source] = mcps_dict[source].get("config", {})
                print(f"[*] Found MCP '{source}' in registry!")

            except Exception as e:
                print(f"X Failed to fetch or parse MCP registry: {e}")
                return

        # 执行落盘写入逻辑
        try:
            # 加载已有的 mcp_config.json
            if os.path.exists(mcp_config_path):
                with open(mcp_config_path, "r", encoding="utf-8") as f:
                    current_config = json.load(f)
            else:
                current_config = {"mcpServers": {}}

            if "mcpServers" not in current_config:
                current_config["mcpServers"] = {}

            env_warning_list = []

            # 合并新增的 MCP Server 配置
            for server_name, server_config in new_mcp_configs.items():
                current_config["mcpServers"][server_name] = server_config
                print(f"  -> Added/Updated MCP server: {server_name}")

                # 智能提醒：如果包含空的 env，提醒用户去填 Key
                if "env" in server_config and any(
                    not v for v in server_config["env"].values()
                ):
                    env_warning_list.append(server_name)

            os.makedirs(os.path.dirname(mcp_config_path), exist_ok=True)
            with open(mcp_config_path, "w", encoding="utf-8") as f:
                json.dump(current_config, f, indent=2, ensure_ascii=False)

            print("[+] Successfully installed MCP configurations.")

            # 打印环境变量配置警告
            if env_warning_list:
                print(
                    "\n[!] IMPORTANT: The following MCPs require Environment Variables (API Keys):"
                )
                for w_mcp in env_warning_list:
                    print(f"    - {w_mcp}")
                print(
                    "    Please edit '.purrcat/mcp_config.json' to fill in the missing values."
                )

        except Exception as e:
            print(f"X Failed to save MCP configuration: {e}")

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
            f"https://raw.githubusercontent.com/PurrPod/graphs/main/{graph_filename}"
        )
        dest_dir = os.path.join(project_root, "src", "harness", "graph")
        os.makedirs(dest_dir, exist_ok=True)
        dest_path = os.path.join(dest_dir, graph_filename)

        print(f"[*] Fetching graph '{graph_name}' from PurrPod/graphs...")
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
                    f"X Error: Graph '{graph_filename}' not found in PurrPod/graphs repository."
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
            "https://github.com/PurrPod/nodes/archive/refs/heads/main.zip"
        )
        dest_dir = os.path.join(
            project_root, "src", "harness", "node", "extensions", source
        )
        subfolder_path = f"nodes/{source}"

        print(f"[*] Fetching official node '{source}' from PurrPod/nodes...")
        if _download_and_extract_subfolder(OFFICIAL_REPO_ZIP, subfolder_path, dest_dir):
            print(f"[+] Successfully installed node '{source}' to {dest_dir}")

    # ---------------------------------------------------------
    # 4. Skill 安装逻辑：支持查表 (Registry) 或直接传入 GitHub 链接
    # ---------------------------------------------------------
    elif ext_type == "skill":
        target_url = source

        # 如果不是 http 开头，说明是短名，需要去 registry.json 查表
        if not target_url.startswith("http"):
            registry_url = (
                "https://raw.githubusercontent.com/PurrPod/skills/main/registry.json"
            )
            print(f"[*] Querying registry for '{source}'...")
            try:
                req = urllib.request.Request(
                    registry_url, headers={"User-Agent": "PurrCat-CLI/1.0"}
                )
                response = urllib.request.urlopen(req)
                registry_data = json.loads(response.read().decode("utf-8"))

                skills_dict = registry_data.get("skills", {})
                if source not in skills_dict:
                    print(f"X Error: Skill '{source}' not found in official registry.")
                    print(f"  Available skills: {', '.join(skills_dict.keys())}")
                    return

                target_url = skills_dict[source].get("source_url")
                print(f"[*] Found '{source}' in registry! Resolving source URL...")
            except Exception as e:
                print(f"X Failed to fetch or parse registry: {e}")
                return

        # 执行原有逻辑：解析最终的 target_url 并执行无头下载与解压
        if target_url and target_url.startswith("http"):
            parsed = _parse_github_url(target_url)
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
            print("X Error: Invalid source URL resolved.")

    else:
        print(f"X Unknown extension type: {ext_type}")
        print("  Supported types: skill, node, graph, mcp")
