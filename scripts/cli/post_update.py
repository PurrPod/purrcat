"""
PurrCat Post-Update Hooks
Handles data migration and cleanup after code updates.
"""

import json
import os
import shutil
import sys


def _get_project_root():
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _setup_path():
    """Add project root to sys.path so src.utils.config is importable."""
    project_root = _get_project_root()
    if project_root not in sys.path:
        sys.path.insert(0, project_root)


def migrate_v1_to_v2():
    """Migrate sensor.json if old keys exist"""
    _setup_path()
    from src.utils.config import SENSOR_CONFIG_PATH

    sensor_path = SENSOR_CONFIG_PATH

    if os.path.exists(sensor_path):
        with open(sensor_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if "old_rss_key" in data:
            data["rss"] = data.pop("old_rss_key")
            with open(sensor_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            print("    [Hook] Migrated sensor.json to new format.")


def clean_legacy_docker_cache():
    """Clean up legacy Docker cache from old versions"""
    project_root = _get_project_root()
    old_cache = os.path.join(project_root, "sandbox", "old_tmp_dir")
    if os.path.exists(old_cache):
        shutil.rmtree(old_cache)
        print("    [Hook] Cleaned up legacy Docker cache.")


def main():
    print("    [Hook] Starting environment checks...")

    try:
        migrate_v1_to_v2()
        clean_legacy_docker_cache()
        print("    [Hook] All post-update tasks completed successfully.")
    except Exception as e:
        print(f"    [Hook Error] {e}")


if __name__ == "__main__":
    main()
