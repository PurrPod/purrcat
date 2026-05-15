"""PurrCat init command - Generate .purrcat configuration files"""
import os
import sys
import json

from scripts.cli.templates import (
    CRON_CONFIG_TEMPLATE,
    MEMEORY_MD_TEMPLATE,
    SOLO_MD_TEMPLATE,
    SOUL_MD_TEMPLATE,
    TODO_MD_TEMPLATE,
    get_model_config_dict,
    get_sensor_config_dict,
    get_file_config_dict,
    get_note_config_dict,
    get_memory_config_dict,
    get_mcp_config_dict,
)


def _get_project_root():
    """Get the project root directory (parent of scripts/)"""
    # __file__ = scripts/cli/cmd_init.py
    # 向上3层: cmd_init.py -> cli/ -> scripts/ -> 项目根目录
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _prompt_overwrite(file_path, force):
    """Prompt user for overwrite confirmation. Returns True if should overwrite."""
    if force:
        return True
    print(f"! File already exists: {file_path}")
    val = input("  Overwrite? (y/N): ").strip().lower()
    if val == "y":
        return True
    print("  [-] Skipped")
    return False


def _generate_model_config(purrcat_dir, force=False):
    """Generate model configuration file"""
    model_path = os.path.join(purrcat_dir, "model.json")

    if os.path.exists(model_path) and not _prompt_overwrite(model_path, force):
        return False

    model_config = get_model_config_dict()
    try:
        with open(model_path, "w", encoding="utf-8") as f:
            json.dump(model_config, f, indent=2, ensure_ascii=False)
        print(f"[+] model.json generated")
        return True
    except Exception as e:
        print(f"X Failed to write model.json: {e}")
        return False


def _generate_sensor_config(purrcat_dir, force=False):
    """Generate sensor configuration file"""
    sensor_path = os.path.join(purrcat_dir, "sensor.json")

    if os.path.exists(sensor_path) and not _prompt_overwrite(sensor_path, force):
        return False

    sensor_config = get_sensor_config_dict()
    try:
        with open(sensor_path, "w", encoding="utf-8") as f:
            json.dump(sensor_config, f, indent=2, ensure_ascii=False)
        print(f"[+] sensor.json generated")
        return True
    except Exception as e:
        print(f"X Failed to write sensor.json: {e}")
        return False


def _generate_file_config(purrcat_dir, force=False):
    """Generate file system configuration file"""
    file_path = os.path.join(purrcat_dir, "file.json")

    if os.path.exists(file_path) and not _prompt_overwrite(file_path, force):
        return False

    file_config = get_file_config_dict()
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(file_config, f, indent=2, ensure_ascii=False)
        print(f"[+] file.json generated")
        return True
    except Exception as e:
        print(f"X Failed to write file.json: {e}")
        return False


def _generate_memory_config(purrcat_dir, force=False):
    """Generate memory system configuration file"""
    memory_path = os.path.join(purrcat_dir, "memory.json")

    if os.path.exists(memory_path) and not _prompt_overwrite(memory_path, force):
        return False

    memory_config = get_memory_config_dict()
    try:
        with open(memory_path, "w", encoding="utf-8") as f:
            json.dump(memory_config, f, indent=2, ensure_ascii=False)
        print(f"[+] memory.json generated")
        return True
    except Exception as e:
        print(f"X Failed to write memory.json: {e}")
        return False


def _generate_mcp_config(purrcat_dir, force=False):
    """Generate MCP configuration file"""
    mcp_path = os.path.join(purrcat_dir, "mcp_config.json")

    if os.path.exists(mcp_path) and not _prompt_overwrite(mcp_path, force):
        return False

    mcp_config = get_mcp_config_dict()
    try:
        with open(mcp_path, "w", encoding="utf-8") as f:
            json.dump(mcp_config, f, indent=2, ensure_ascii=False)
        print(f"[+] mcp_config.json generated")
        return True
    except Exception as e:
        print(f"X Failed to write mcp_config.json: {e}")
        return False


def _generate_note_config(purrcat_dir, force=False):
    """Generate agent note configuration file"""
    agent_dir = os.path.join(purrcat_dir, "agent")
    os.makedirs(agent_dir, exist_ok=True)

    note_path = os.path.join(agent_dir, "note.json")

    if os.path.exists(note_path) and not _prompt_overwrite(note_path, force):
        return False

    note_config = get_note_config_dict()
    try:
        with open(note_path, "w", encoding="utf-8") as f:
            json.dump(note_config, f, indent=2, ensure_ascii=False)
        print(f"[+] agent/note.json generated")
        return True
    except Exception as e:
        print(f"X Failed to write agent/note.json: {e}")
        return False


def _generate_core_files(purrcat_dir, force=False):
    """Generate core directory files"""
    core_dir = os.path.join(purrcat_dir, "core")
    os.makedirs(core_dir, exist_ok=True)

    results = []

    cron_path = os.path.join(core_dir, "cron.json")
    if os.path.exists(cron_path) and not _prompt_overwrite(cron_path, force):
        results.append(("cron.json", False))
    else:
        try:
            with open(cron_path, "w", encoding="utf-8") as f:
                f.write(CRON_CONFIG_TEMPLATE)
            print(f"[+] core/cron.json generated")
            results.append(("cron.json", True))
        except Exception as e:
            print(f"X Failed to write core/cron.json: {e}")
            results.append(("cron.json", False))

    memory_md_path = os.path.join(core_dir, "MEMORY.md")
    if os.path.exists(memory_md_path) and not _prompt_overwrite(memory_md_path, force):
        results.append(("MEMORY.md", False))
    else:
        try:
            with open(memory_md_path, "w", encoding="utf-8") as f:
                f.write(MEMEORY_MD_TEMPLATE)
            print(f"[+] core/MEMORY.md generated")
            results.append(("MEMORY.md", True))
        except Exception as e:
            print(f"X Failed to write core/MEMORY.md: {e}")
            results.append(("MEMORY.md", False))

    solo_md_path = os.path.join(core_dir, "SOLO.md")
    if os.path.exists(solo_md_path) and not _prompt_overwrite(solo_md_path, force):
        results.append(("SOLO.md", False))
    else:
        try:
            with open(solo_md_path, "w", encoding="utf-8") as f:
                f.write(SOLO_MD_TEMPLATE)
            print(f"[+] core/SOLO.md generated")
            results.append(("SOLO.md", True))
        except Exception as e:
            print(f"X Failed to write core/SOLO.md: {e}")
            results.append(("SOLO.md", False))

    soul_md_path = os.path.join(core_dir, "SOUL.md")
    if os.path.exists(soul_md_path) and not _prompt_overwrite(soul_md_path, force):
        results.append(("SOUL.md", False))
    else:
        try:
            with open(soul_md_path, "w", encoding="utf-8") as f:
                f.write(SOUL_MD_TEMPLATE)
            print(f"[+] core/SOUL.md generated")
            results.append(("SOUL.md", True))
        except Exception as e:
            print(f"X Failed to write core/SOUL.md: {e}")
            results.append(("SOUL.md", False))

    todo_md_path = os.path.join(core_dir, "TODO.md")
    if os.path.exists(todo_md_path) and not _prompt_overwrite(todo_md_path, force):
        results.append(("TODO.md", False))
    else:
        try:
            with open(todo_md_path, "w", encoding="utf-8") as f:
                f.write(TODO_MD_TEMPLATE)
            print(f"[+] core/TODO.md generated")
            results.append(("TODO.md", True))
        except Exception as e:
            print(f"X Failed to write core/TODO.md: {e}")
            results.append(("TODO.md", False))

    return all(ok for _, ok in results)


def run_init(force=False):
    """Generate .purrcat configuration directory"""
    project_root = _get_project_root()
    purrcat_dir = os.path.join(project_root, ".purrcat")

    if os.path.exists(purrcat_dir):
        if force:
            print(f"[*] Directory exists: {purrcat_dir} (force mode, overwriting)")
        else:
            print(f"[!] .purrcat directory already exists, continue initialization?")
            val = input("  All config files will be confirmed one by one (Y/N): ").strip().lower()
            if val != "y":
                print("  Cancelled")
                return
    else:
        try:
            os.makedirs(purrcat_dir, exist_ok=True)
            print(f"[+] Created config directory: {purrcat_dir}")
        except Exception as e:
            print(f"X Failed to create directory: {e}")
            sys.exit(1)

    print("")
    print("[*] Starting config file generation, please confirm each...")

    results = []
    results.append(("model", _generate_model_config(purrcat_dir, force=False)))
    results.append(("sensor", _generate_sensor_config(purrcat_dir, force=False)))
    results.append(("file", _generate_file_config(purrcat_dir, force=False)))
    results.append(("mcp", _generate_mcp_config(purrcat_dir, force=False)))
    results.append(("memory", _generate_memory_config(purrcat_dir, force=False)))
    results.append(("note", _generate_note_config(purrcat_dir, force=False)))
    results.append(("core", _generate_core_files(purrcat_dir, force=False)))

    print("")
    print("[*] Summary:")
    generated = sum(1 for _, ok in results if ok)
    skipped = sum(1 for _, ok in results if not ok)
    print(f"    Generated: {generated}")
    print(f"    Skipped: {skipped}")

    if generated > 0:
        print("")
        print("[*] Next steps for a quick start:")
        print("    Edit .purrcat/model.json to add your agent model and API Key")
        print("    Then run: purrcat start")