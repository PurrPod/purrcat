import os
import asyncio
from datetime import datetime
from pathlib import Path
from src.tool.utils.format import text_response, error_response
from src.agent.session_store import SessionStore
from src.agent.sub_runner import (
    cancel_sub_branch,
    run_dag_graph,
    ensure_sub_loop,
)
from src.utils.config import AGENT_VM_DIR, get_file_config
from src.utils.path import convert_sandbox_path

# 沙盒根目录（预计算，用于快速放行）
_AGENT_VM_ROOT = os.path.normcase(os.path.abspath(AGENT_VM_DIR))


def _has_write_permission(target_path: str) -> bool:
    """
    BrainStorm 内部专属的轻量级写权限校验器，避免引入 filesystem 导致循环导入。
    核心逻辑与底层文件系统保持一致。
    """
    # 1. 路径映射：将沙盒路径转换为宿主机实际路径
    path = convert_sandbox_path(target_path)

    # 沙盒内是 agent 自己的电脑，无论用户是否配置权限，一律全放行
    try:
        if (
            os.path.commonpath([os.path.normcase(path), _AGENT_VM_ROOT])
            == _AGENT_VM_ROOT
        ):
            return True
    except ValueError:  # Windows 下跨盘符等情况
        pass

    target_norm = os.path.normcase(path)
    target_path_obj = Path(target_norm)

    # 2. 读取系统的文件权限配置
    config = get_file_config()
    perms = config.get("permissions", {})

    best_match_len = -1
    best_perm = config.get("default_permission", "readonly")

    # 3. 匹配算法：支持绝对路径和通配符
    for perm_type in ["blocked", "readonly", "writable"]:
        for rule in perms.get(perm_type, []):
            rule_norm = os.path.normcase(rule)
            is_match = False

            if os.path.isabs(rule_norm):
                try:
                    if os.path.commonpath([target_norm, rule_norm]) == rule_norm:
                        is_match = True
                except ValueError:
                    pass

            if not is_match:
                for current_node in [target_path_obj] + list(target_path_obj.parents):
                    if current_node.match(rule_norm):
                        is_match = True
                        break

            if is_match:
                match_weight = len(rule_norm)
                if rule_norm == target_norm:
                    match_weight += 10000  # 绝对精准匹配权重最高
                if match_weight > best_match_len:
                    best_match_len = match_weight
                    best_perm = perm_type

    return best_perm == "writable"


def _render_plan_markdown(main_plan: list = None, sub_branches: list = None) -> str:
    """把 BrainStorm 指定的计划解析成 Markdown 总计划，供会话级 @PLAN 引用。"""
    main_plan = main_plan or []
    sub_branches = sub_branches or []

    lines = [
        "# BrainStorm 总计划",
        "",
        f"- 刷新时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- 主干步骤：{len(main_plan)} 步",
        f"- 后台支线：{len(sub_branches)} 个",
        "",
        "## 主干 Main 分支执行大纲",
    ]
    if main_plan:
        lines.extend(f"{i}. {step}" for i, step in enumerate(main_plan, 1))
    else:
        lines.append("（无）")

    lines.extend(["", "## 后台支线任务"])
    if sub_branches:
        for branch in sub_branches:
            lines.append(f"### {branch.get('branch_id', '未命名支线')}")
            lines.append(f"- 任务：{branch.get('action', '')}")
            lines.append("- 交付物：")
            deliverables = branch.get("deliverable") or []
            if deliverables:
                lines.extend(f"  - `{item}`" for item in deliverables)
            else:
                lines.append("  （无）")
            depends_on = branch.get("depends_on") or []
            lines.append(f"- 依赖：{'、'.join(depends_on) if depends_on else '无'}")
            lines.append("")
    else:
        lines.append("（无）")

    return "\n".join(lines).rstrip() + "\n"


def BrainStorm(
    action: str,
    main_plan: list = None,
    sub_branches: list = None,
    target_branch_id: str = None,
    _tool_call_id: str = None,
    **kwargs,
) -> str:
    try:
        # 🚫 核心拦截：打工仔分支没有决策和裁员权限
        if kwargs.get("_is_sub_branch"):
            return error_response(
                "越权被拒：后台子分支无权调用 BrainStorm 工具进行递归派发或强制取消操作！"
            )

        if action == "cancel":
            if not target_branch_id:
                return error_response("参数错误：缺少 target_branch_id")

            # 统一走 cancel_sub_branch：它同时兼容 display id（b1）与内部 id
            # （{batch}_b1），并在并发多批次下跨批次匹配同名分支全部斩杀。
            if cancel_sub_branch(target_branch_id):
                return text_response(
                    f"✅ 斩杀信号已成功下发！后台分支 `{target_branch_id}` 已被强制终止。",
                    "🛑 分支已终止",
                )
            else:
                return error_response(
                    f"未在系统中捕捉到活跃运行的后台分支 `{target_branch_id}`。"
                )

        elif action == "create":
            # 🌟 新增：事前独立校验多文件的写入权限
            if sub_branches:
                for branch in sub_branches:
                    deliverables = branch.get("deliverable", [])
                    if not isinstance(deliverables, list):
                        return error_response(
                            f"参数错误：分支 `{branch.get('branch_id')}` 的 deliverable 必须是文件路径数组(array)。"
                        )

                    for target_file in deliverables:
                        if not _has_write_permission(target_file):
                            return error_response(
                                f"✋ 派发失败：分支 `{branch.get('branch_id')}` 的交付物路径 `{target_file}` 缺乏写入权限。\n"
                                f"安全策略拦截：系统拒绝派发此任务。请先调用 Request 工具为该路径申请 file_write 权限，或修改目标路径为沙盒内(/agent_vm)路径。"
                            )

            msg_lines = ["🚀 [系统] 脑暴大纲与任务排期已成功落盘生效！"]

            if main_plan:
                msg_lines.append("\n### 📌 【主干 Main 分支后续执行大纲】")
                for i, step in enumerate(main_plan, 1):
                    msg_lines.append(f"**Step {i}**. {step}")

            if sub_branches:
                msg_lines.append(
                    f"\n后台支线任务 ({len(sub_branches)}个) 已成功递交底层引擎，在暗中开辟独立线程快马加鞭运转中。"
                )

            # 📄 把本次计划整体刷新到当前会话的 plan.md，供范式 @PLAN 引用
            from src.agent.manager import AgentManager

            manager = AgentManager()
            main_session_id = manager.get_active_session_id()
            if main_session_id:
                try:
                    SessionStore.save_session_plan(
                        main_session_id,
                        _render_plan_markdown(main_plan, sub_branches),
                    )
                except Exception as e:
                    msg_lines.append(f"\n⚠️ 总计划落盘失败：{e}")

            msg_lines.append(
                "\n💡 指示：工具已闭环，你不需要进行任何循环查询。请立即按照你刚才定下的 Main 主线计划第一步去沙盒开展工作。子任务结果出来后系统会自动通知。"
            )
            final_response_text = "\n".join(msg_lines)

            if sub_branches:
                main_history = manager._agent.get_history()

                # 🌟 从尾部往前定位本批次的 assistant 消息（带 tool_calls）。
                # BS 被调度器延后到批次末尾执行，此刻其后可能已跟了同批次
                # 其它工具的返回结果（这些结果会随快照进入子代理上下文），
                # 因此不能只看 history[-1]。
                assistant_idx = -1
                for i in range(len(main_history) - 1, -1, -1):
                    msg = main_history[i]
                    if msg.get("role") == "assistant" and msg.get("tool_calls"):
                        assistant_idx = i
                        break

                if assistant_idx >= 0:
                    # 引入 json 模块以确保安全的字符串化
                    import json

                    assistant_msg = main_history[assistant_idx]
                    answered_ids = {
                        m.get("tool_call_id")
                        for m in main_history[assistant_idx + 1 :]
                        if m.get("role") == "tool"
                    }
                    unanswered = [
                        tc
                        for tc in assistant_msg["tool_calls"]
                        if tc.get("id") not in answered_ids
                    ]

                    # 定位本工具自己的 tool_call：优先用调度器注入的
                    # _tool_call_id，兜底按函数名匹配
                    own_tc = None
                    if _tool_call_id:
                        own_tc = next(
                            (tc for tc in unanswered if tc.get("id") == _tool_call_id),
                            None,
                        )
                    if own_tc is None:
                        own_tc = next(
                            (
                                tc
                                for tc in unanswered
                                if tc.get("function", {}).get("name") == "BrainStorm"
                            ),
                            None,
                        )

                    # 1) 塞入 BS 自己的伪造结果（绝对安全的纯字符串）
                    if own_tc:
                        # 拿取原始响应
                        raw_resp = text_response(
                            final_response_text, "🚀 脑暴计划已生效"
                        )
                        # 模拟 dispatch_tool 的安全策略，如果是字典就转 JSON 字符串
                        safe_content = (
                            json.dumps(raw_resp, ensure_ascii=False)
                            if isinstance(raw_resp, dict)
                            else str(raw_resp)
                        )
                        main_history.append(
                            {
                                "role": "tool",
                                "tool_call_id": own_tc["id"],
                                "name": "BrainStorm",
                                "content": safe_content,
                            }
                        )
                        answered_ids.add(own_tc["id"])

                    # 2) 兜底补全其余未应答的调用（如同批次并存的另一个
                    #    BrainStorm），防止子代理上下文 toolchain 断裂触发 400
                    for tc in unanswered:
                        if tc.get("id") in answered_ids:
                            continue
                        main_history.append(
                            {
                                "role": "tool",
                                "tool_call_id": tc["id"],
                                "name": tc.get("function", {}).get("name", ""),
                                "content": (
                                    "【系统提示】该工具调用与 BrainStorm 同批次发出，"
                                    "其返回结果未注入本子代理上下文，请勿依赖此占位内容。"
                                ),
                            }
                        )

                loop = ensure_sub_loop()
                asyncio.run_coroutine_threadsafe(
                    run_dag_graph(sub_branches, main_session_id, main_history),
                    loop,
                )

            return text_response(final_response_text, "🚀 脑暴计划已生效")

        return error_response("无效的 action 指令")

    except Exception as e:
        return error_response(f"BrainStorm 调度引擎崩溃: {e}")
