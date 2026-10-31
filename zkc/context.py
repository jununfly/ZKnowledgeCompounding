"""ZKC · context 拓扑装配算子（P3.4，生产落地 spike-06）。

设计要点（spike-06 已验证）：
- 一次「装配」= 一个 transform -> 一个 context + 其若干 member；所有产物带 produced_by，
  撤消 transform 时 context + members 级联消失（PG 走 FK CASCADE，Memory 走等价级联）。
- T4.1 自闭环 vs 更高维 context：discover 用 pgvector k-NN 提议更高维 context 的种子邻域。
- 人审成员（produced_by=NULL）可单独增删，不受 transform 级联撤影响。

本算子** provider 无关**：只依赖注入的 Storage 门面，内存 fake 与 PG 同行为，免 DB 单测。

T4.1 收尾（原 spike-06 open 项）：
- **自动命名**：`ContextNamer` 复用 distill 的 `LLM = Callable[[str],str]` seam（可注入、免重依赖），
  LLM 不可达/返回空时退化为确定性关键词命名（`fallback_name`），绝不因命名失败阻断提议。
- **触发策略（人审闸门）**：`propose_higher_dim` 只「提议」不「自动创建」——过相似度阈值 +
  最小近邻数 + 去重闸门（同种子已存在则跳过）三道关后才 `would_create=True`；真正落库由
  `create_higher_dim`（或未来 UI/review_queue 人审确认）显式触发。契合稀缺注意力原则：
  系统决定「此刻该聚合什么」，但写图动作交人确认。全局频率上限（每日提议数）属调度层，
  不在本切片内（见 §8 限定）。

铁律（P1.4）：scope 仅限 ('self_loop' | 'higher_dim')，越界即 ValueError；阈值走 zkc.tuning。
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Callable, Optional
from uuid import UUID

from . import tuning
from .distill import LLM
from .repository.protocols import Storage

# LLM 命名 system prompt（确定性、可注入、与具体模型解耦）
HIGHER_DIM_NAMING_SYSTEM = (
    "你是一个知识图谱聚合命名器。下面是一组彼此语义相近的知识条目文本。"
    "请用简短的中文短语（不超过 8 个字，或英文不超过 6 个词）概括它们的共同高层主题。"
    "只输出这个标题本身，不要解释、不要引号、不要列表。"
)

# 确定性命名用的停用字符（CJK 常见虚词 + 标点/空白）
_STOPCHARS = set("的了一是在不有我他这中大为上和是与就都也要会能可去你那它此该等之其为以于对其或")
_TOKEN_RE = re.compile(r"[a-z0-9]+|[\u4e00-\u9fff]")


def _clean_title(raw: str) -> str:
    """解析 LLM 命名输出：取首非空行、去首尾引号、超额截断。失败返回空串。"""
    t = (raw or "").strip()
    first = next((ln.strip() for ln in t.splitlines() if ln.strip()), "")
    first = first.strip('"\'""''')
    if len(first) > 32:
        first = first[:32]
    return first


def fallback_name(member_texts: list[str], n_members: int) -> str:
    """确定性退化命名：无 LLM 时从成员文本提取高频词作标题。

    仅作降级路径——真实命名靠 LLM（`ContextNamer.name`）。人审闸门保证退化名可被改名。
    """
    cnt = Counter()
    for text in member_texts:
        for tok in _TOKEN_RE.findall((text or "").lower()):
            if tok in _STOPCHARS:
                continue
            # 丢弃孤立 ascii 单字符（噪声），保留 CJK 单字与英文词
            if len(tok) == 1 and tok.isascii():
                continue
            cnt[tok] += 1
    top = [t for t, _ in sorted(cnt.items(), key=lambda kv: (-kv[1], kv[0]))[:2]]
    if top:
        return f"聚合：{'/'.join(top)}（{n_members}条）"
    return f"未命名聚合（{n_members}条）"


class ContextNamer:
    """更高维 context 命名（provider 无关）。

    注入 `llm: LLM` 即走 LLM 命名；`llm=None` 走 `fallback_name` 确定性命名。
    两种路径都不抛异常、都返回非空字符串。
    """

    def name(self, member_texts: list[str], llm: Optional[LLM] = None) -> str:
        non_empty = [t for t in member_texts if t]
        if llm is not None:
            joined = "\n".join(f"- {t}" for t in non_empty) or "(无文本)"
            raw = llm(f"{HIGHER_DIM_NAMING_SYSTEM}\n\n条目：\n{joined}")
            cleaned = _clean_title(raw)
            if cleaned:
                return cleaned
        return fallback_name(non_empty, len(non_empty))


@dataclass
class HigherDimProposal:
    """T4.1 更高维 context 提议（不落库，等显式创建或人审确认）。"""

    seed_node_id: UUID
    neighbor_ids: list[UUID]            # 通过相似度阈值的近邻（不含种子自身）
    similarities: list[float]           # 与 neighbor_ids 一一对应
    suggested_title: str                # 由 ContextNamer 给出（含退化路径）
    would_create: bool                  # 三道闸门全过才 True
    reason: str                         # would_create 为 False 时说明原因
    existing_context_id: Optional[UUID] = None  # 已存在则记录，便于调用方跳转


class ContextAssembler:
    """context 拓扑装配算子（provider 无关）。"""

    def __init__(self, store: Storage, namer: Optional[ContextNamer] = None) -> None:
        self.store = store
        self.namer = namer or ContextNamer()

    def assemble(
        self,
        scope: str,
        node_ids: list[UUID],
        title: str | None = None,
        weight: float = 1.0,
    ) -> tuple[UUID, UUID]:
        """装配一个 context。返回 (context_id, transform_id)。"""
        return self.store.assemble_context(scope, node_ids, title, weight)

    def revert(self, transform_id: UUID) -> int:
        """撤消装配：删 transform -> 级联撤 context + members。返回撤掉的 context 数。"""
        return self.store.revert_assembly(transform_id)

    def discover(self, seed_node_id: UUID, k: int = 5) -> list:
        """T4.1：种子节点的 k 近邻（PG 走 pgvector；内存 fake 返回空）。"""
        return self.store.discover_higher_dim(seed_node_id, k)

    def add_human_member(
        self, context_id: UUID, node_id: UUID, weight: float = 1.0
    ) -> None:
        """人审添加成员（produced_by=NULL，可单独删）。"""
        self.store.contexts.add_member_human(context_id, node_id, weight)

    def remove_human_member(self, context_id: UUID, node_id: UUID) -> None:
        """仅删人审成员（produced_by IS NULL）；transform 产成员须走 revert。"""
        self.store.contexts.remove_member_human(context_id, node_id)

    def propose_higher_dim(
        self,
        seed_node_id: UUID,
        k: int = 5,
        llm: Optional[LLM] = None,
        *,
        sim_threshold: float | None = None,
        min_members: int | None = None,
    ) -> HigherDimProposal:
        """T4.1 触发策略（人审闸门版）：只提议、不自动创建。

        闸门：① 近邻余弦相似度 ≥ sim_threshold；② 通过阈值的近邻数 ≥ min_members；
        ③ 同种子已存在 higher_dim context 则跳过（去重，防重复提议）。三关全过 →
        would_create=True，否则 reason 说明未过哪关。命名由 ContextNamer 给出。
        """
        sim_threshold = (
            tuning.get("CONTEXT_HIGHER_DIM_SIM_THRESHOLD") if sim_threshold is None
            else sim_threshold
        )
        min_members = (
            int(tuning.get("CONTEXT_HIGHER_DIM_MIN_MEMBERS")) if min_members is None
            else int(min_members)
        )
        neighbors = self.store.discover_higher_dim(seed_node_id, k)
        kept = [n for n in neighbors if n.get("sim", 0.0) >= sim_threshold]
        neighbor_ids = [n["id"] for n in kept]
        sims = [float(n["sim"]) for n in kept]

        # 命名文本：种子标题 + 各近邻标题
        seed = self.store.nodes.get(seed_node_id)
        seed_title = seed.title if seed else ""
        member_texts = [seed_title] + [n.get("title") or "" for n in kept]
        suggested_title = self.namer.name(member_texts, llm)

        # 去重闸门
        existing = self.store.contexts.find_higher_dim_for_seed(seed_node_id)
        if existing is not None:
            return HigherDimProposal(
                seed_node_id=seed_node_id,
                neighbor_ids=neighbor_ids,
                similarities=sims,
                suggested_title=suggested_title,
                would_create=False,
                reason="higher_dim context 已存在，跳过重复提议",
                existing_context_id=existing,
            )
        if len(neighbor_ids) < min_members:
            return HigherDimProposal(
                seed_node_id=seed_node_id,
                neighbor_ids=neighbor_ids,
                similarities=sims,
                suggested_title=suggested_title,
                would_create=False,
                reason=(
                    f"近邻不足：{len(neighbor_ids)} < {min_members}"
                    f"（相似度阈值 {sim_threshold}）"
                ),
                existing_context_id=None,
            )
        return HigherDimProposal(
            seed_node_id=seed_node_id,
            neighbor_ids=neighbor_ids,
            similarities=sims,
            suggested_title=suggested_title,
            would_create=True,
            reason="通过相似度阈值、最小近邻数与去重闸门",
            existing_context_id=None,
        )

    def create_higher_dim(
        self, proposal: HigherDimProposal, llm: Optional[LLM] = None
    ) -> tuple[UUID, UUID]:
        """T4.1 显式创建：把通过的提议落库为 higher_dim context。

        成员 = 种子 + 近邻；标题取提议的 suggested_title。未过闸门（would_create=False）
        则拒绝创建并附原因——写图动作只能由显式调用（或人审确认）触发。
        """
        if not proposal.would_create:
            raise ValueError(f"拒绝创建更高维 context：{proposal.reason}")
        full = [proposal.seed_node_id] + list(proposal.neighbor_ids)
        title = proposal.suggested_title or self.namer.name([], llm)
        return self.assemble("higher_dim", full, title=title)
