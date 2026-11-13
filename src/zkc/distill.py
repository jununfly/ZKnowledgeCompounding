"""ZKC · 半自动蒸馏算子（P3.1，生产落地 distill-llm 调研）。

设计要点（调研 docs/archive/research/distill-llm-2026-10-29-draft.md）：
- MVP 组合 = Ollama(本地推理) + Instructor(结构化抽取与校验重试) + LangGraph(编排 + HITL)，
  provider 收敛到 Instructor 统一接口。但**本切片不引入这些重依赖**：
  1) 本仓沙箱/本机装不上（langgraph/instructor 重依赖），且
  2) 调研关键提醒——没有任何候选提供 ZKC 的蒸馏语义（去繁 → 元认知 + topic + 反向连接），
     该语义必须由 ZKC 自建。
- 本切片交付：ZKC 自建蒸馏语义的数据模型 + 校验规则，以及一个 **provider 无关**的算子
  （LLM 调用通过可注入 callable 传入）。这样在真实 Ollama/Instructor 接线之前即可单测，
  不阻断整条 critical path（蒸馏结构化切片的前驱依赖）。
- 蒸馏结构化接线已落地：JSON 契约解析 + 手写校验重试（Instructor 等价，决策见
  蒸馏设计决策）+ 真实 Ollama 客户端（zkc.llm.make_distill_llm，铁律内置）。
  LangGraph 不引入：HITL 语义已由 expiry.apply_distill 失败回落 review_queue 承载；
  score 表见 migrations/0007_llm_call_score + expiry.apply_distill 落库点。

铁律（P1.4）：本模块阈值走 zkc.tuning；蒸馏语义**不变式**（每条 claim 须引用≥1 来源）
属于逻辑约束而非可调阈值，保留为模块常量并显式标注。
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Callable, Optional, Sequence
from uuid import UUID

from . import scheduling
from . import tuning
from .repository.protocols import Storage

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
    # 结构化接线（Instructor 等价手写重试）：本次蒸馏实际消耗的 LLM 尝试次数（含首次），
    # 供 score 表（llm_call_score.attempts）记录重试成本。
    attempts: int = 1


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


# 结构化 JSON 契约（蒸馏结构化接线）：prompt 层 schema 提示，等同 Instructor Mode.JSON 的
# 提示层行为（铁律①：禁用 /v1+response_format 与 Instructor Mode.JSON_SCHEMA/OPENAI_TOOLS——
# 对 qwen3.5-mlx 永久挂死；JSON 合规由提示约束 + 调用方正则抽取兜底）。
DISTILL_SCHEMA_HINT = (
    '输出必须是且仅是如下结构的 JSON（字段名逐字遵守）：\n'
    '{"claims": [{"text": str, "topic": str, '
    '"citations": [来源节点uuid字符串数组，每条至少1个]}]}\n'
    'citations 只能引用材料中给出的 [uuid]，不得编造。'
)

_JSON_OBJ_RE = re.compile(r"\{.*\}", re.DOTALL)


def _extract_json(raw: str) -> Optional[dict]:
    """从 LLM 文本提取第一个 JSON 对象（宽松，容忍围栏/前后缀）；失败返回 None。"""
    m = _JSON_OBJ_RE.search(raw or "")
    if not m:
        return None
    try:
        obj = json.loads(m.group(0))
    except ValueError:
        return None
    return obj if isinstance(obj, dict) else None


def _parse_json_output(
    raw: str, source_texts: Sequence[tuple[UUID, str]]
) -> Optional[DistillationResult]:
    """解析结构化 JSON 契约为 DistillationResult（蒸馏主路径）。

    契约：{"claims": [{text, topic, citations: [uuid, ...]}]}。
    - citations 里非源集合的 uuid 一律丢弃（与文本解析同语义：不许编造来源）；
    - claim 文本中的 [[uuid]] 内联标记也并入引用（宽容 LLM 混用两种标记）；
    - JSON 缺 claims 数组 / claims 非列表 → 返回 None（调用方走文本 fallback 或重试）。
    """
    obj = _extract_json(raw)
    if obj is None or not isinstance(obj.get("claims"), list):
        return None
    id_set = {sid for sid, _ in source_texts}
    claims: list[MetaClaim] = []
    for item in obj["claims"]:
        if not isinstance(item, dict) or not str(item.get("text") or "").strip():
            return None  # 结构残缺 → 整体视为解析失败（重试修正比静默丢 claim 安全）
        cited: list[UUID] = []
        for tok in (item.get("citations") or []):
            try:
                uid = UUID(str(tok))
            except (ValueError, TypeError):
                continue
            if uid in id_set and uid not in cited:
                cited.append(uid)
        for tok in _CITE_RE.findall(str(item.get("text") or "")):
            try:
                uid = UUID(tok)
            except ValueError:
                continue
            if uid in id_set and uid not in cited:
                cited.append(uid)
        claims.append(MetaClaim(
            text=str(item["text"]).strip(),
            topic=str(item.get("topic") or "(unclassified)"),
            citations=[Citation(sid) for sid in cited],
            reverse_links=list(cited),
        ))
    if not claims:
        return None
    return DistillationResult(claims=claims)


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
    max_attempts: Optional[int] = None,
) -> DistillationResult:
    """对单个节点执行一次蒸馏（ZKC 语义层 + 可注入 LLM + 结构化校验重试）。

    - source_texts: [(源节点id, 文本), ...]，提供反向连接与引用目标。
    - llm: provider 无关的文本生成 callable（真实环境见 zkc.llm.make_distill_llm）。
    - 结构化接线（Instructor 等价）：prompt 带 JSON schema 提示；解析顺序
      JSON 契约 → 旧文本标记 fallback；任一解析成功但**语义校验失败**（引用不足），
      或两种解析都失败 → 带一条短修正提示重调 LLM，最多 max_attempts 次
      （tuning.DISTILL_MAX_ATTEMPTS）。超限抛最后一次的 DistillationError。
    - 返回**已通过语义校验**的结果（attempts 记录实际尝试次数）。
    """
    n = int(max_attempts if max_attempts is not None
            else tuning.get("DISTILL_MAX_ATTEMPTS"))
    base = _build_prompt(node_id, source_texts, system_prompt)
    prompt = base + "\n\n" + DISTILL_SCHEMA_HINT
    last_err: Optional[Exception] = None
    for attempt in range(1, n + 1):
        p = prompt
        if attempt > 1 and last_err is not None:
            # 非膨胀重试（spike-10 先例）：每次从头重建 prompt，只追加一条短修正提示。
            p = (prompt + f"\n上一次输出未通过校验（{str(last_err)[:80]}）。"
                 "请重新输出完整 JSON，字段名逐字遵守，每条 claim 的 citations "
                 "至少含 1 个材料中的来源 uuid。")
        raw = llm(p)
        result = _parse_json_output(raw, source_texts)
        if result is None:
            result = _parse_llm_output(raw, source_texts)
        try:
            result = validate_result(result)
            result.attempts = attempt
            return result
        except DistillationError as e:
            last_err = e
    raise last_err  # type: ignore[misc]


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


# ---------------------------------------------------------------- 撤销路径（残余 2 hook）

def revert_claim(store: Storage, claim_id, produced_by=None) -> dict:
    """删除一条 claim 并级联重算其 evidence 节点的「已捕获」基线（单程票边界 1）。

    这是 ``scheduling.recompute_baseline_on_capture_loss`` 的**唯一调用方 hook**：claim 被删
    → 其 evidence_refs 节点的「已捕获」状态可能消失 → 立即按未捕获基线重算并写 D7
    capture-loss 审计，禁止调度层静默变化。若节点仍被其他 claim 捕获，recompute 内部 no-op。

    返回 ``{deleted, claim_id, evidence_node_ids, recomputed:[...], reason}``；``recomputed``
    每项含 ``node_id`` 与 ``recompute_baseline_on_capture_loss`` 的返回值（applied/old_days/
    new_days/tier/reason）。

    注：artifact 撤销见同级 ``revert_artifact``——ArtifactRepository 已落地（残余 A 消解），
    两个捕获载体（claim / modeling_artifact）的撤销语义完全同构。
    """
    claim = store.claims.get(claim_id)
    if claim is None:
        return dict(deleted=False, claim_id=claim_id, evidence_node_ids=[],
                    recomputed=[], reason="claim not found")
    evidence = list(claim.evidence_refs)
    store.claims.delete(claim.id)
    recomputed = []
    for nid in evidence:
        res = scheduling.recompute_baseline_on_capture_loss(
            store, nid, produced_by=produced_by)
        recomputed.append(dict(node_id=nid, **res))
    return dict(deleted=True, claim_id=claim_id, evidence_node_ids=evidence,
                recomputed=recomputed,
                reason="claim deleted; cascaded capture-loss recompute to evidence nodes")


def revert_artifact(store: Storage, artifact_id, produced_by=None) -> dict:
    """删除一条建模产物并级联重算其 evidence 节点的「已捕获」基线（残余 A hook）。

    与 ``revert_claim`` 完全同构：ArtifactRepository.delete 后，对每条 evidence_refs
    节点调 ``scheduling.recompute_baseline_on_capture_loss``（写 D7 capture-loss 审计，
    禁止调度层静默变化）。若节点仍被其他 claim/artifact 捕获，recompute 内部 no-op。

    返回 ``{deleted, artifact_id, evidence_node_ids, recomputed:[...], reason}``。
    """
    artifact = store.artifacts.get(artifact_id)
    if artifact is None:
        return dict(deleted=False, artifact_id=artifact_id, evidence_node_ids=[],
                    recomputed=[], reason="artifact not found")
    evidence = list(artifact.evidence_refs)
    store.artifacts.delete(artifact.id)
    recomputed = []
    for nid in evidence:
        res = scheduling.recompute_baseline_on_capture_loss(
            store, nid, produced_by=produced_by)
        recomputed.append(dict(node_id=nid, **res))
    return dict(deleted=True, artifact_id=artifact_id, evidence_node_ids=evidence,
                recomputed=recomputed,
                reason="artifact deleted; cascaded capture-loss recompute to evidence nodes")
