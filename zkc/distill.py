"""ZKC · 半自动蒸馏算子（P3.1，生产落地 distill-llm 调研）。

设计要点（调研 docs/research/distill-llm-2026-10-29-draft.md）：
- MVP 组合 = Ollama(本地推理) + Instructor(结构化抽取与校验重试) + LangGraph(编排 + HITL)，
  provider 收敛到 Instructor 统一接口。但**本切片不引入这些重依赖**：
  1) 本仓沙箱/本机装不上（langgraph/instructor 重依赖），且
  2) 调研关键提醒——没有任何候选提供 ZKC 的蒸馏语义（去繁 → 元认知 + topic + 反向连接），
     该语义必须由 ZKC 自建。
- 本切片交付：ZKC 自建蒸馏语义的数据模型 + 校验规则，以及一个 **provider 无关**的算子
  （LLM 调用通过可注入 callable 传入）。这样在真实 Ollama/Instructor 接线之前即可单测，
  不阻断整条 critical path（1-5-1 是 1-5-2~1-5-5 的 blocks 前驱）。
- 后续切片：接 Instructor + Ollama 真实结构化抽取、接 LangGraph HITL、加 score 表/rubric。

铁律（P1.4）：本模块阈值走 zkc.tuning；蒸馏语义**不变式**（每条 claim 须引用≥1 来源）
属于逻辑约束而非可调阈值，保留为模块常量并显式标注。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, Optional, Sequence
from uuid import UUID

from . import tuning

# ZKC 蒸馏语义不变式（DISTILL_MIN_CITATIONS_PER_CLAIM，见 tuning）：
# 去繁不是凭空捏造——每条元认知 claim 至少引用 1 个来源。
# 这是 distillation-semantics-native=0 的那一层——候选均不提供，必须自建。

# LLM 输出中的来源引用标记：[[<uuid>]]，算子据此把 claim 反向连接到源节点。
_CITE_RE = re.compile(r"\[\[([0-9a-fA-F-]{36})\]\]")

# LLM 调用契约：输入 prompt，输出 LLM 原始文本（provider 无关）。
LLM = Callable[[str], str]


@dataclass
class Citation:
    """一条来源引用：指向某个源节点 + 可选片段。"""
    source_node_id: UUID
    snippet: Optional[str] = None


@dataclass
class MetaClaim:
    """蒸馏产出的元认知 claim（去繁后的高层结论），必须带回向连接。"""
    text: str
    topic: str
    citations: list[Citation] = field(default_factory=list)
    # 反向连接：被蒸馏并支撑本 claim 的源节点 id 列表（去繁→反向连接语义）。
    reverse_links: list[UUID] = field(default_factory=list)


@dataclass
class DistillationResult:
    """一次蒸馏的结构化产出。"""
    claims: list[MetaClaim] = field(default_factory=list)
    notes: str = ""


class DistillationError(ValueError):
    """蒸馏语义校验失败（ZKC 自建规则），区别于底层 IO/解析错误。"""


def validate_result(result: DistillationResult) -> DistillationResult:
    """强制 ZKC 蒸馏语义：每条 claim 至少 1 条来源引用，否则抛 DistillationError。

    这是没有任何候选提供的语义层（调研 distillation-semantics-native=0），必须自建。
    """
    if not result.claims:
        raise DistillationError("distillation produced no claims")
    min_c = int(tuning.get("DISTILL_MIN_CITATIONS_PER_CLAIM"))
    for c in result.claims:
        if len(c.citations) < min_c:
            raise DistillationError(
                f"claim has {len(c.citations)} citations, need >= {min_c}: {c.text!r}")
    return result


def _build_prompt(
    node_id: UUID,
    source_texts: Sequence[tuple[UUID, str]],
    system_prompt: Optional[str],
) -> str:
    head = (system_prompt
            or "将以下材料蒸馏为去繁后的元认知结论；每条结论须用 [[源节点uuid]] 标记其来源。")
    body = "\n".join(f"[{sid}] {txt}" for sid, txt in source_texts)
    return f"{head}\n\n材料：\n{body}\n\n节点：{node_id}"


def _parse_llm_output(raw: str, source_texts: Sequence[tuple[UUID, str]]) -> DistillationResult:
    """解析 LLM 文本为结构化结果。

    本切片不依赖 Instructor：用 [[uuid]] 标记做轻量解析，建立可注入 LLM 的 seam。
    真实切片由 Instructor 的 Pydantic 模型替换（自动校验重试的结构化抽取）。
    """
    text = (raw or "").strip()
    id_set = {sid for sid, _ in source_texts}
    cited: list[UUID] = []
    for tok in _CITE_RE.findall(text):
        try:
            uid = UUID(tok)
        except ValueError:
            continue
        if uid in id_set and uid not in cited:
            cited.append(uid)
    claim = MetaClaim(
        text=text or "(empty)",
        topic="(unclassified)",
        citations=[Citation(sid) for sid in cited],
        reverse_links=list(cited),
    )
    return DistillationResult(claims=[claim])


def distill_node(
    node_id: UUID,
    source_texts: Sequence[tuple[UUID, str]],
    llm: LLM,
    *,
    system_prompt: Optional[str] = None,
) -> DistillationResult:
    """对单个节点执行一次蒸馏（ZKC 语义层 + 可注入 LLM）。

    - source_texts: [(源节点id, 文本), ...]，提供反向连接与引用目标。
    - llm: provider 无关的文本生成 callable（真实环境由 Instructor + Ollama 实现）。
    - 返回**已通过语义校验**的结果；不满足不变式则抛 DistillationError。
    """
    prompt = _build_prompt(node_id, source_texts, system_prompt)
    raw = llm(prompt)
    result = _parse_llm_output(raw, source_texts)
    return validate_result(result)


class DistillationOperator:
    """蒸馏算子（provider 无关）。注入 llm 即可运行，免重依赖单测。"""

    def __init__(self, llm: LLM):
        self.llm = llm

    def distill(
        self,
        node_id: UUID,
        source_texts: Sequence[tuple[UUID, str]],
        *,
        system_prompt: Optional[str] = None,
    ) -> DistillationResult:
        return distill_node(node_id, source_texts, self.llm, system_prompt=system_prompt)
