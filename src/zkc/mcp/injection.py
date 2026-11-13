"""ZKC · 不可信文档的注入标记检测（注入防护）。

关键边界：检测只用于**留痕与标记**，绝不把匹配结果当作可执行指令。
外部文档经 agent 推入 ZKC 后，内容一律按纯文本存储；即使 agent 被注入，
它后续能调的写 tool 仍受白名单/黑名单与 HITL 归因闸约束（见 handlers.py）。
"""
from __future__ import annotations

from typing import List, Tuple

INJECTION_MARKERS: Tuple[str, ...] = (
    # ADR-0004 黑名单四类危险写
    "distill/trigger", "interval_adjustment", "meta_claim",
    "history/delete", "history/update",
    # 常见的提示注入话术
    "ignore previous instructions", "ignore all previous",
    "忽略之前的指令", "忽略上述", "忽略前面", "覆盖系统指令",
    "call tool", "invoke tool", "调用工具", "调用 tool",
)


def detect_injection_markers(text: str) -> List[str]:
    """返回内容里命中的标记列表（去重、保持声明顺序）；普通文本返回空列表。"""
    if not text:
        return []
    lowered = text.lower()
    return [marker for marker in INJECTION_MARKERS if marker.lower() in lowered]


__all__ = ["INJECTION_MARKERS", "detect_injection_markers"]
