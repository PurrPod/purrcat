import asyncio
from src.tool.filesystem.utils import can_write
from src.tool.brainstorm._shared import (
    build_create_message,
    build_tool_reply,
    find_assistant_tool_batch,
    pick_own_tool_call,
    render_plan_markdown,
    unanswered_tool_calls,
)
from src.tool.utils.format import text_response, error_response
from src.agent.session_store import SessionStore
from src.agent.sub_runner import (
    cancel_sub_branch,
    run_dag_graph,
    ensure_sub_loop,
)


def _has_write_permission(target_path: str) -> bool:
    return can_write(target_path)


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

            # 📄 把本次计划整体刷新到当前会话的 plan.md，供范式 @PLAN 引用
            from src.agent.manager import AgentManager

            manager = AgentManager()
            main_session_id = manager.get_active_session_id()
            plan_error = None
            if main_session_id:
                try:
                    SessionStore.save_session_plan(
                        main_session_id,
                        render_plan_markdown(main_plan, sub_branches),
                    )
                except Exception as e:
                    plan_error = str(e)

            final_response_text = build_create_message(
                main_plan, sub_branches, plan_error
            )

            if sub_branches:
                main_history = manager._agent.get_history()

                # 🌟 从尾部往前定位本批次的 assistant 消息（带 tool_calls）。
                # BS 被调度器延后到批次末尾执行，此刻其后可能已跟了同批次
                # 其它工具的返回结果（这些结果会随快照进入子代理上下文），
                # 因此不能只看 history[-1]。
                assistant_idx = find_assistant_tool_batch(main_history)

                if assistant_idx >= 0:
                    # 引入 json 模块以确保安全的字符串化
                    import json

                    answered_ids, unanswered = unanswered_tool_calls(
                        main_history, assistant_idx
                    )

                    # 定位本工具自己的 tool_call：优先用调度器注入的
                    # _tool_call_id，兜底按函数名匹配
                    own_tc = pick_own_tool_call(unanswered, _tool_call_id)

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
                            build_tool_reply(own_tc, safe_content, name="BrainStorm")
                        )
                        answered_ids.add(own_tc["id"])

                    # 2) 兜底补全其余未应答的调用（如同批次并存的另一个
                    #    BrainStorm），防止子代理上下文 toolchain 断裂触发 400
                    for tc in unanswered:
                        if tc.get("id") in answered_ids:
                            continue
                        main_history.append(
                            build_tool_reply(
                                tc,
                                "【系统提示】该工具调用与 BrainStorm 同批次发出，"
                                "其返回结果未注入本子代理上下文，请勿依赖此占位内容。",
                            )
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
