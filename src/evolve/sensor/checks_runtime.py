"""Sensor L1 真网关协议夹具检查（SPEC-020）。

执行顺序、超时、失败文案与抓包集合是报告契约的一部分，不在此处做聚合。
"""

import json
import os
import shutil
import time

from src.evolve.sensor.fixtures import (
    FIXTURE_SESSION_ID,
    _ALIVE_GRACE,
    _AUTH_PROMPT_TIMEOUT,
    _HANDSHAKE_TIMEOUT,
    _GatewayFixture,
    _child_env,
    _kill_tree,
    _prompt_text,
)


def runtime_checks(
    script_path: str, sandbox_root: str, declared: list, iteration_dir: str
) -> tuple[list, dict]:
    cases = []

    def add(case_id, title, passed, detail, level="error"):
        cases.append(
            {
                "id": case_id,
                "layer": "L1",
                "title": title,
                "pass": bool(passed),
                "detail": detail,
                "level": level,
            }
        )

    uv_path = shutil.which("uv")
    if not uv_path:
        add(
            "uv_available",
            "uv 可用",
            False,
            "宿主机 PATH 中找不到 uv，无法拉起 sensor 子进程",
        )
        return cases, {"transcript": []}

    env = _child_env(declared)
    stderr_path = os.path.join(iteration_dir, "sensor_stderr.log")
    fixture = _GatewayFixture(script_path, sandbox_root, env, stderr_path)

    try:
        try:
            fixture.start()
        except Exception as e:
            add("uv_spawn", "uv run 拉起并完成握手", False, f"进程拉起失败: {e}")
            return cases, {"transcript": []}

        # 1. 握手（同时证明 PEP 723 依赖可解析安装）
        got_handshake = fixture.wait_for(fixture.has_handshake, _HANDSHAKE_TIMEOUT)
        add(
            "uv_spawn",
            "uv run 拉起并完成握手",
            got_handshake,
            "进程拉起成功，initialize 与 session/new 均已发出"
            if got_handshake
            else f"超时 {_HANDSHAKE_TIMEOUT:.0f}s 未收到完整握手；"
            "通常是 PEP 723 依赖装不上或启动即崩溃（详见 sensor_stderr.log）",
        )

        handshake_elapsed = None
        if got_handshake:
            first_t, second_t = None, None
            for entry in fixture.transcript:
                if entry["dir"] != "sensor→host":
                    continue
                try:
                    msg = json.loads(entry["raw"])
                except json.JSONDecodeError:
                    continue
                if msg.get("id") == 1 and first_t is None:
                    first_t = entry["t"]
                elif msg.get("id") == 2 and second_t is None:
                    second_t = entry["t"]
            if first_t is not None and second_t is not None:
                handshake_elapsed = round(second_t - first_t, 3)

        add(
            "handshake_order",
            "握手顺序 initialize(1) → session/new(2)",
            got_handshake and fixture.handshake_ok(),
            f"顺序正确，间隔 {handshake_elapsed}s"
            if got_handshake and fixture.handshake_ok()
            else "握手缺失或顺序错乱（必须先是 initialize，再是 session/new）",
        )

        # 2. 空凭证逼出失败上报
        got_prompt = fixture.wait_for(
            lambda: bool(fixture.prompts), _AUTH_PROMPT_TIMEOUT
        )
        add(
            "failure_report",
            "缺凭证冷启动上报失败详情",
            got_prompt,
            f"已捕获 session/prompt（t={fixture.auth_prompt_at and round(fixture.auth_prompt_at - fixture.started_at, 2)}s）"
            if got_prompt
            else f"超时 {_AUTH_PROMPT_TIMEOUT:.0f}s 未发出任何 session/prompt；"
            "缺凭证时必须上报失败详情，不能静默哑掉",
        )

        prompt_text = ""
        if got_prompt:
            _, prompts_snapshot, _ = fixture.snapshot()
            prompt_text = _prompt_text(prompts_snapshot[0].get("params", {}))

        # 3. sessionId 回填
        prompts_with_sid = []
        if got_prompt:
            _, prompts_snapshot, _ = fixture.snapshot()
            for prompt in prompts_snapshot:
                prompts_with_sid.append(prompt.get("params", {}).get("sessionId"))
        sid_ok = bool(prompts_with_sid) and all(
            sid == FIXTURE_SESSION_ID for sid in prompts_with_sid
        )
        add(
            "sid_backfill",
            "sessionId 回填正确",
            sid_ok,
            f"session/prompt 携带了网关下发的 sessionId={FIXTURE_SESSION_ID}"
            if sid_ok
            else f"session/prompt 的 sessionId={prompts_with_sid!r}，"
            f"应为网关回填的 {FIXTURE_SESSION_ID!r}（回填错了会导致注入静默失效）",
        )

        # 4. 失败详情质量：必须点名缺失的凭证
        if got_prompt:
            hit_keys = [k for k in declared if k in prompt_text]
            add(
                "failure_detail",
                "失败详情含缺失凭证名",
                bool(hit_keys),
                f"命中凭证名 {hit_keys}"
                if hit_keys
                else "上报文本里没有出现已声明的凭证名，Agent 无从判断缺什么",
            )

        # 5. 抗污染：塞垃圾行
        for junk in ("hello", "{", "[]", "不是 JSON 的一行", "x" * 4000):
            fixture.send_raw(junk)
        time.sleep(1.0)
        add(
            "garbage_tolerance",
            "非法输入不崩溃",
            fixture.alive(),
            "注入 5 类垃圾行后进程仍存活"
            if fixture.alive()
            else "注入垃圾行后进程已退出",
        )

        # 6. 未知 method 下发
        fixture.send(
            {
                "jsonrpc": "2.0",
                "method": "_purrcat/unknown_probe",
                "params": {"probe": True},
            }
        )
        # 7. 正常下发（Agent 回复 / 文件 / 轮次结束）
        fixture.send(
            {
                "jsonrpc": "2.0",
                "method": "session/update",
                "params": {
                    "sessionId": FIXTURE_SESSION_ID,
                    "update": {
                        "sessionUpdate": "agent_message_chunk",
                        "content": {"type": "text", "text": "pong"},
                    },
                },
            }
        )
        fixture.send(
            {
                "jsonrpc": "2.0",
                "method": "_purrcat/file",
                "params": {
                    "sessionId": FIXTURE_SESSION_ID,
                    "name": "probe.txt",
                    "content_b64": "cHJvYmU=",
                },
            }
        )
        fixture.send(
            {
                "jsonrpc": "2.0",
                "method": "_purrcat/turn_end",
                "params": {"sessionId": FIXTURE_SESSION_ID},
            }
        )
        time.sleep(1.5)
        add(
            "dispatch_tolerance",
            "未知/正常下发均不崩溃",
            fixture.alive(),
            "未知 method + update/file/turn_end 下发后进程仍存活"
            if fixture.alive()
            else "处理下发消息时进程退出（网络请求可能阻塞在主循环里）",
        )

        # 8. 错误响应容忍：夹具已故意对 session/prompt 回 error
        add(
            "error_response",
            "收到 error 响应不崩溃",
            fixture.alive(),
            "夹具对 session/prompt 回 -32000 错误后进程仍存活"
            if fixture.alive()
            else "收到错误响应后进程退出",
        )

        # 9. stdout 纯净
        _, _, polluted_snapshot = fixture.snapshot()
        add(
            "stdout_purity",
            "stdout 仅承载 JSON-RPC",
            not polluted_snapshot,
            f"抓到 {len(fixture.from_sensor)} 条合法 JSON-RPC"
            if not polluted_snapshot
            else f"发现 {len(polluted_snapshot)} 行非协议输出：{polluted_snapshot[:3]}",
        )

        # 10. 永不退出
        time.sleep(_ALIVE_GRACE)
        add(
            "no_exit",
            "空转不退出",
            fixture.alive(),
            f"静置 {_ALIVE_GRACE:.0f}s 后进程仍存活"
            if fixture.alive()
            else "进程自行退出，违反「严禁退出主进程」铁律",
        )

        # 11. 杀后重启可拉起
        _kill_tree(fixture.proc)
        time.sleep(1.0)
        restart_stderr = os.path.join(iteration_dir, "sensor_stderr_restart.log")
        second = _GatewayFixture(script_path, sandbox_root, env, restart_stderr)
        try:
            second.start()
            restarted = second.wait_for(second.has_handshake, _HANDSHAKE_TIMEOUT)
        except Exception:
            restarted = False
        finally:
            second.close()
        add(
            "restart",
            "杀死后可重新拉起",
            restarted,
            "再次启动并完成握手，未出现双实例冲突"
            if restarted
            else "重启后未能完成握手，热重启/看门狗恢复会失效",
        )

    finally:
        transcript = list(fixture.transcript)
        fixture.close()

    return cases, {"transcript": transcript}
