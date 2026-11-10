"""指南生成器：模板正文见 prompts.py。"""

from .prompts import build_mcp_guide


def generate_mcp_guide(mcp_name: str, goal: str = "", agent_vm_dir: str = "") -> str:
    return build_mcp_guide(mcp_name, goal, agent_vm_dir)
