"""PurrCat update command - Update framework from GitHub Releases"""

import os
import subprocess
import sys

CONDA_CMD = "conda.bat" if os.name == "nt" else "conda"


def _get_project_root():
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _run_cmd(command, cwd=None, capture=False):
    try:
        if capture:
            result = subprocess.run(
                command, cwd=cwd, check=True, capture_output=True, text=True
            )
            return True, result.stdout.strip()
        else:
            subprocess.run(command, cwd=cwd, check=True)
            return True, ""
    except subprocess.CalledProcessError as e:
        return False, str(e)
    except FileNotFoundError:
        return False, "Command not found."


def run_update(target_version=None):
    """Execute release-based update workflow"""
    print("Checking PurrCat repository...")
    print("==========================================")

    project_root = _get_project_root()
    git_dir = os.path.join(project_root, ".git")

    if not os.path.exists(git_dir):
        print("X Error: Not a git repository. Cannot update.")
        sys.exit(1)

    print("[*] Fetching latest releases from GitHub...")
    success, _ = _run_cmd(["git", "fetch", "--tags", "--force"], cwd=project_root)
    if not success:
        print("X Failed to fetch from GitHub. Check your network.")
        sys.exit(1)

    latest_version = "main"

    if target_version:
        if not target_version.startswith("v"):
            target_version = f"v{target_version}"

        success, stdout = _run_cmd(
            ["git", "tag", "-l", target_version], cwd=project_root, capture=True
        )
        if not stdout:
            print(
                f"X Error: Version tag '{target_version}' not found in the repository."
            )
            print("  Available recent versions:")
            _, tags = _run_cmd(
                ["git", "tag", "--sort=-v:refname"], cwd=project_root, capture=True
            )
            for t in tags.split("\n")[:5]:
                if t.strip():
                    print(f"    - {t}")
            sys.exit(1)

        latest_version = target_version
        print(f"[*] Target version specified: {latest_version}")

    else:
        success, stdout = _run_cmd(
            ["git", "tag", "--sort=-v:refname"], cwd=project_root, capture=True
        )
        tags = [t for t in stdout.split("\n") if t.strip()]

        if not tags:
            print("[!] No releases (tags) found. Falling back to main branch...")
        else:
            latest_version = tags[0]
            print(f"[*] Found latest stable release: {latest_version}")

    print(f"[*] Checking out to {latest_version}...")
    _run_cmd(["git", "reset", "--hard"], cwd=project_root)
    _run_cmd(["git", "checkout", latest_version], cwd=project_root)

    print(f"[*] Syncing Conda environment for {latest_version}...")
    env_file = os.path.join(project_root, "environment.yml")
    if os.path.exists(env_file):
        _run_cmd(
            [CONDA_CMD, "env", "update", "-f", env_file, "--prune"], cwd=project_root
        )

    post_update_script = os.path.join(project_root, "scripts", "cli", "post_update.py")
    if os.path.exists(post_update_script):
        print("[*] Running post-update migrations...")
        hook_success, hook_err = _run_cmd(
            [CONDA_CMD, "run", "-n", "PurrCat", "python", post_update_script],
            cwd=project_root,
        )
        if not hook_success:
            print(f"X Post-update hook failed: {hook_err}")
            sys.exit(1)

    print("==========================================")
    print(f"Congratulations! PurrCat is now at version: {latest_version}")
