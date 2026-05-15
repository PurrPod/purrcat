"""PurrCat install command - Extension manager for skills, nodes, and graphs"""

import io
import os
import re
import sys
import urllib.request
import zipfile


def _get_project_root():
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _download_and_extract_subfolder(zip_url, subfolder_path, dest_dir):
    """Download ZIP and extract only the specified subfolder in memory."""
    print(f"[*] Downloading from {zip_url} ...")
    try:
        response = urllib.request.urlopen(zip_url)
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
    """Execute install logic (适配 PurrPod 官方架构及第三方深度 Skill 提取)"""
    project_root = _get_project_root()

    print(f"Installing {ext_type}...")
    print("==========================================")

    if ext_type in ["node", "graph"]:
        OFFICIAL_REPO_ZIP = (
            f"https://github.com/PurrPod/{ext_type}/archive/refs/heads/main.zip"
        )

        dest_dir = os.path.join(project_root, "src", "harness", ext_type, source)

        subfolder_path = f"{ext_type}/{source}"

        print(f"[*] Fetching official {ext_type} '{source}' from PurrPod/{ext_type}...")
        if _download_and_extract_subfolder(OFFICIAL_REPO_ZIP, subfolder_path, dest_dir):
            print(f"[+] Successfully installed {ext_type} '{source}' to {dest_dir}")

    elif ext_type == "skill":
        if source.startswith("http"):
            parsed = _parse_github_url(source)
            if not parsed:
                print("X Error: Invalid GitHub URL format.")
                print(
                    "  Expected: https://github.com/owner/repo/tree/branch/path/to/skill"
                )
                sys.exit(1)

            skill_name = os.path.basename(parsed["path"].rstrip("/"))
            dest_dir = os.path.join(project_root, "skills", skill_name)

            zip_url = f"https://github.com/{parsed['owner']}/{parsed['repo']}/archive/refs/heads/{parsed['branch']}.zip"

            print(
                f"[*] Fetching third-party skill '{skill_name}' from {parsed['owner']}/{parsed['repo']}"
            )
            print(f"    Target path in repo: {parsed['path']}")

            if _download_and_extract_subfolder(zip_url, parsed["path"], dest_dir):
                print(
                    f"[+] Successfully installed skill '{skill_name}' to skills/{skill_name}"
                )
        else:
            print("X Error: Currently, skill installation requires a full GitHub URL.")
            print(
                "  Example: purrcat install skill https://github.com/user/repo/tree/main/very/deep/path/weather_skill"
            )

    else:
        print(f"X Unknown extension type: {ext_type}")
        print("  Supported types: skill, node, graph")
