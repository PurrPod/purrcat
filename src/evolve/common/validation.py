"""Evolve 校验报告的结论摘要。"""


def validation_summary(report: dict) -> tuple:
    """把 validator 的 report 归一化为 (是否通过, 中文结论)。"""
    if report["ok"]:
        return True, f"校验通过（错误 0，警告 {report['warnings']}）"
    bad = [
        c["title"]
        for c in report["checks"]
        if not c["ok"] and c.get("level") == "error"
    ]
    return False, f"校验未通过（{report['errors']} 处错误）：" + "；".join(bad[:5])
