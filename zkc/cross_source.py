"""ZKC · 跨源强制算子（P3.2，生产落地 Spike 11）。

设计要点（spikes/spike-11-cross-source-enforcement/README.md，4B×3 稳定 3/3 实证）：
- 跨源综合失败是**算子/提示层**问题、非模型规模问题——旧结合算子只「软性」要求
  global 层，小模型自然退化成「一条来源一条 claim，从不真正综合」（Spike 10 缺口）。
- 两点改造（都在算子层，不碰模型）：
  1. 提示层硬约束：主生成 prompt 明确要求 ≥ CROSS_SOURCE_MIN_ASSERTIONS 条跨源
     综合断言（每条 evidence_ids 含 ≥2 个不同来源 id，并说明来源间关系）；
  2. 算子补全回路（bounded，单次）：主生成后数跨源 claim 数，不足则触发**一次**
     跨源补全调用，把补生成的 claim merge 进产物再跑一次引用强制。不无限循环。
- R14 埋点：report 记录 main_latency_ms / completion_latency_ms / completion_fired，
  触发率与额外延迟由调用方按 run 聚合；超预算可关 complete_on_shortfall 退回主生成。

与 Spike 11 的差异（生产化裁剪）：
- 不引 instructor/openai 重依赖：LLM 调用全部走可注入 callable（同 distill.py seam），
  真实接线（Instructor + Ollama）属 1-5-6 后续切片。
- 阈值走 zkc.tuning（P1.4 铁律）；Spike 11 算子严格优于 Spike 05 baseline
  （4B 3/3 vs 2/3），故漏斗/引用强制作为本算子必要基础设施随本切片进来；
  repository 落库接线 + 级联撤销联调属 1-5-3。
- schema 与 Spike 05 ModelingArtifact 保持同构（刻意不变——证明是算子层可解）。
"""
from __future__ import annotations

import time
from typing import Callable, Optional

from pydantic import BaseModel, Field

from . import tuning

# LLM 调用契约（provider 无关；真实环境由 Instructor + Ollama 实现）。
SummarizeFn = Callable[[dict, str], str]        # (source, query) -> summary
ScoreFn = Callable[[str, str], float]           # (summary, query) -> 0..1
GenerateFn = Callable[[str], "CrossSourceArtifact"]  # prompt -> structured artifact
CompleteFn = Callable[[str, list, list, int], object]  # (query, kept, existing, need)


# ---------------------------------------------------------------- 结构化产物契约
class ArtifactClaim(BaseModel):
    """建模产物下的一条结构化断言（带引用，Spike 05 schema 同构）。"""

    statement: str = Field(description="该建模产物下的一条结构化断言")
    level: str = Field(description="principle | pattern | antipattern | tradeoff")
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_ids: list[str] = Field(
        description="支撑该断言的来源条目 id（必须来自给定来源集合）",
    )


class CrossSourceArtifact(BaseModel):
    """结合算子产物：带引用的结构化建模产物，不是摘要堆砌。

    与 Spike 05 ModelingArtifact 同构（spike-05 models.py）；跨源硬约束
    是算子层职责，不进 schema——schema 不变是 Spike 11 的控制变量。
    """

    title: str = Field(description="产物标题（一句话命名该模型/方法论）")
    kind: str = Field(description="methodology | mental_model | tradeoff_map")
    claims: list[ArtifactClaim] = Field(min_length=1, description="1 条以上带引用断言")
    local: list[str] = Field(
        default_factory=list,
        description="local 层：各来源实体级要点（可空；空层是质量信号）",
    )
    global_insights: list[str] = Field(
        default_factory=list,
        alias="global",
        description="global 层：跨来源关系链/更高维模式（可空；空层是质量信号）",
    )
    methodology_steps: list[str] = Field(
        default_factory=list,
        description="若 kind=methodology：可执行步骤序列",
    )

    model_config = {"populate_by_name": True}


# ---------------------------------------------------------------- 引用强制
def enforce_citations(artifact: dict, source_ids: set[str]) -> dict:
    """过滤幻觉引用（不在来源集合中的 evidence_id），丢弃引用全灭的 claim。

    ZKC 结合语义不变式：建模产物没有有效引用就不得存在——全部 claim 引用
    崩塌时抛 ValueError（调用方决定放弃整次产物）。
    """
    kept_claims = []
    dropped = 0
    for claim in artifact.get("claims", []):
        valid = [e for e in claim.get("evidence_ids", []) if e in source_ids]
        if not valid:
            dropped += 1
            continue
        kept_claims.append(dict(claim, evidence_ids=valid))
    total = dropped + len(kept_claims)
    if not kept_claims:
        raise ValueError(
            f"artifact rejected: all {total} claims lost their citations "
            f"(hallucinated provenance)"
        )
    return dict(
        artifact,
        claims=kept_claims,
        evidence_refs=sorted({e for c in kept_claims for e in c["evidence_ids"]}),
        _dropped_claims=dropped,
    )


def count_cross_source(claims: list[dict]) -> int:
    """跨源综合断言数：evidence_ids 含 >=2 个**不同**来源 id 的 claim 数。"""
    return sum(1 for c in claims if len(set(c.get("evidence_ids", []))) >= 2)


# ---------------------------------------------------------------- 算子
class CrossSourceOperator:
    """RCS 漏斗 + 双层合并 + 跨源硬约束 + 单次有界补全回路。

    注入契约（单测用 stub 即可跑通机制，不依赖模型）：
      summarize(source, query) -> str
      score(summary, query) -> float
      generate(prompt) -> CrossSourceArtifact（或属性等价物）
      complete(query, kept, existing_claims, need) -> 含 .claims / ["claims"] 的对象
    """

    def __init__(
        self,
        summarize: SummarizeFn,
        score: ScoreFn,
        generate: GenerateFn,
        complete: Optional[CompleteFn] = None,
        *,
        max_sources: Optional[int] = None,
        min_cross_source: Optional[int] = None,
        complete_on_shortfall: bool = True,
    ):
        self._summarize = summarize
        self._score = score
        self._generate = generate
        self._complete = complete
        self.max_sources = int(max_sources if max_sources is not None
                               else tuning.get("COMBINE_MAX_SOURCES"))
        self.min_cross_source = int(
            min_cross_source if min_cross_source is not None
            else tuning.get("CROSS_SOURCE_MIN_ASSERTIONS"))
        self.complete_on_shortfall = complete_on_shortfall

    # ---- RCS 漏斗（per-source 摘要 -> 打分 -> 截断；Spike 05 同机制）
    def _funnel(self, query: str, sources: list[dict]):
        scored = []
        for src in sources:
            summary = self._summarize(src, query)
            s = self._score(summary, query)
            scored.append({"source": src, "summary": summary, "score": s})
        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[: self.max_sources], scored[self.max_sources:]

    # ---- 提示层（硬约束是本算子的核心变量）
    def _build_prompt(self, query: str, kept: list[dict], min_cs: int) -> str:
        local = "\n".join(
            f"- [{k['source']['id'][:8]}] {k['source']['title']}"
            f"（支撑度 {k['score']:.2f}）：{k['summary']}"
            for k in kept
        )
        ids = ", ".join(k["source"]["id"] for k in kept)
        return (
            f"问题：「{query}」\n\n"
            f"以下是经漏斗筛选的来源要点（local 层），请把它们结合成一个**更高一层的建模产物**"
            f"（方法论/心智模型/权衡图），不要摘要堆砌：\n{local}\n\n"
            f"要求：\n"
            f"1. 每条断言必须引用支撑它的来源 id，只能从这些 id 中选：{ids}\n"
            f"2. global 层写跨来源的关系/模式，而非任何单条来源的复述\n"
            f"3. 【硬约束】claims 中必须至少包含 {min_cs} 条**跨源综合断言**——"
            f"每条 evidence_ids 含「>=2 个不同来源 id」，并明确说明这些来源之间是"
            f"相互印证 / 冲突 / 互补 / 还是共同指向某个更高维模式\n"
            f"4. kind=methodology 时给出可执行步骤\n"
            f"5. 使用证据 id（完整 id）标注 evidence_ids"
        )

    def _build_complete_prompt(self, query: str, kept: list[dict],
                               existing: list[dict], need: int, ids: str) -> str:
        local = "\n".join(
            f"- [{k['source']['id'][:8]}] {k['source']['title']}：{k['summary']}"
            for k in kept
        )
        exist_txt = "\n".join(
            f"- {c.get('statement', '')}（引 {c.get('evidence_ids', [])}）"
            for c in existing
        ) or "（无）"
        return (
            f"问题：「{query}」\n\n来源要点：\n{local}\n\n"
            f"已有断言（不要重复，仅用于避免重叠）：\n{exist_txt}\n\n"
            f"请补充至少 {need} 条【跨源综合断言】：\n"
            f"- 每条必须引用 >=2 个不同来源 id，只能从 {ids} 中选；\n"
            f"- 说明这些来源之间的关系（相互印证 / 冲突 / 互补 / 共同指向某模式）；\n"
            f"- 字段：statement / level / confidence / evidence_ids（完整 id）。"
        )

    def _default_complete(self, query, kept, existing_claims, need):
        """缺省补全 = 复用同一 generate 注入（单次、有界）。"""
        ids = ", ".join(k["source"]["id"] for k in kept)
        prompt = self._build_complete_prompt(query, kept, existing_claims, need, ids)
        return self._generate(prompt)

    @staticmethod
    def _normalize_claims(extra) -> list[dict]:
        """补全输出归一：只保留真跨源（>=2 个不同来源 id）的 claim。"""
        raw = (extra.get("claims", []) if isinstance(extra, dict)
               else getattr(extra, "claims", []))
        out = []
        for c in raw:
            cc = c if isinstance(c, dict) else c.model_dump(by_alias=True)
            if len(set(cc.get("evidence_ids", []))) >= 2:
                out.append(cc)
        return out

    # ---- 入口
    def combine(self, query: str, sources: list[dict]) -> dict:
        """返回 {artifact, report}；引用全崩塌时抛 ValueError（无据产物不得存在）。"""
        t0 = time.perf_counter()
        kept, dropped = self._funnel(query, sources)
        source_ids = {s["id"] for s in sources}
        kept_ids = [k["source"]["id"] for k in kept]

        raw = self._generate(self._build_prompt(query, kept, self.min_cross_source))
        artifact = enforce_citations(raw.model_dump(by_alias=True), source_ids)
        main_latency_ms = (time.perf_counter() - t0) * 1000.0

        n_cross = count_cross_source(artifact["claims"])
        completion_fired = False
        completion_latency_ms: Optional[float] = None
        hook = self._complete or (self._default_complete
                                  if self.complete_on_shortfall else None)
        if self.complete_on_shortfall and n_cross < self.min_cross_source and hook:
            completion_fired = True
            t1 = time.perf_counter()
            need = self.min_cross_source - n_cross
            extra = hook(query, kept, artifact["claims"], need)
            normalized = self._normalize_claims(extra)
            if normalized:
                merged = dict(artifact, claims=artifact["claims"] + normalized)
                try:
                    artifact = enforce_citations(merged, source_ids)
                except ValueError:
                    # 补全 claim 引用全崩 -> 保留主生成产物，不崩溃（best-effort 强制）
                    pass
            completion_latency_ms = (time.perf_counter() - t1) * 1000.0

        final_n_cross = count_cross_source(artifact["claims"])
        return {
            "artifact": artifact,
            "report": {
                "query": query,
                "kept": [{"id": k["source"]["id"], "title": k["source"]["title"],
                          "summary": k["summary"], "score": k["score"]} for k in kept],
                "dropped": [{"id": k["source"]["id"], "title": k["source"]["title"],
                             "score": k["score"]} for k in dropped],
                "kept_ids": kept_ids,
                # R14 埋点：补全触发率与额外延迟由调用方按 run 聚合本字段
                "completion_fired": completion_fired,
                "main_latency_ms": round(main_latency_ms, 3),
                "completion_latency_ms": (round(completion_latency_ms, 3)
                                          if completion_latency_ms is not None else None),
                "n_cross_source_final": final_n_cross,
                "min_cross_source": self.min_cross_source,
                "quality": {
                    "local_empty": not artifact.get("local"),
                    "global_empty": not (artifact.get("global")
                                         or artifact.get("global_insights")),
                    "dropped_claims": artifact.get("_dropped_claims", 0),
                },
            },
        }
