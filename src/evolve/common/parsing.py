"""Evolve 共用 JSON 解析与容错（忠实保留原 evaluator 行为）。"""

import json
import re

# 评分载荷自身的字段：命中任一即认为已是裁判结果本体，不再剥壳
EVAL_KEYS = {"assertion_results", "summary", "pass", "reason", "grading_data"}


def unwrap_envelope(value):
    """剥掉 {type,data} 端口信封（最多三层），取出真正的载荷"""
    for _ in range(3):
        if not isinstance(value, dict) or "data" not in value:
            break
        if EVAL_KEYS & set(value.keys()):
            break
        value = value["data"]
    return value


def json_objects_in(text: str):
    """扫描文本中所有平衡的 {...} 片段（跳过字符串内部的括号）"""
    for start, ch in enumerate(text):
        if ch != "{":
            continue
        depth, in_str, escape = 0, False, False
        for i in range(start, len(text)):
            c = text[i]
            if in_str:
                if escape:
                    escape = False
                elif c == "\\":
                    escape = True
                elif c == '"':
                    in_str = False
                continue
            if c == '"':
                in_str = True
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    yield text[start : i + 1]
                    break


def try_load_dict(text: str) -> dict:
    """尽力把文本解析成 dict：标准 → 宽松 → json_repair → 再剥一层字符串化 JSON"""
    candidates = [text]
    try:
        from json_repair import repair_json

        repaired = repair_json(text, return_objects=True)
        if isinstance(repaired, str) and repaired.strip() and repaired != text:
            candidates.append(repaired)
    except Exception:
        pass

    for cand in candidates:
        for loader in (json.loads, lambda s: json.loads(s, strict=False)):
            try:
                parsed = loader(cand)
            except Exception:
                continue
            # 双重编码：把整个 JSON 当字符串输出过一层
            if isinstance(parsed, str):
                try:
                    parsed = json.loads(parsed)
                except Exception:
                    continue
            if isinstance(parsed, dict):
                return parsed
    return {}


def extract_eval_json(raw) -> tuple:
    """把裁判产出解析成 (dict | None, 原始文本)。

    None 表示完全不可解析，调用方必须把原始文本写进失败理由，禁止静默判负。
    兼容：端口信封、JSON 字符串、```json 代码围栏、散文里夹带的 JSON 片段。
    """
    value = unwrap_envelope(raw)
    if isinstance(value, dict):
        return value, ""
    raw_text = (
        value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    )
    text = raw_text.strip()
    if not text:
        return None, raw_text

    # 1) 整体就是 JSON
    parsed = try_load_dict(text)
    if parsed:
        return parsed, raw_text

    # 2) ```json 代码围栏
    for block in re.findall(r"```(?:json)?\s*([\s\S]*?)```", text, re.IGNORECASE):
        parsed = try_load_dict(block.strip())
        if parsed:
            return parsed, raw_text

    # 3) 散文里夹带的 JSON 片段：命中断言/统计字段者优先，同级取最后一个
    best = {}
    for chunk in json_objects_in(text):
        parsed = try_load_dict(chunk)
        if not parsed:
            continue
        if "assertion_results" in parsed or "summary" in parsed or "pass" in parsed:
            best = parsed
    if best:
        return best, raw_text

    return None, raw_text
