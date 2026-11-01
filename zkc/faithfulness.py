"""ZKC · 忠实度闸门（P3.5，生产落地 Spike 12/13/13b）。

研究结论链（本模块的依据，均已 sealed）：
- Spike 10：字面 rubric（verbatim/overlap/citation_hit）**抓不到内容幻觉**——好抽象
  与无据编造的字面重叠都低，rubric 分不清二者。rubric 只能给出「抄袭/拼接」红旗。
- Spike 12：分解式 LLM-as-judge（拆原子事实→逐条核验→确定性推导 overall）机制成立，
  判定能力已验证；但 4B/9B 在 16GB 本机均被实证否决（~2min/~6min 每条 + 不产 JSON）。
- Spike 13b-probe：本地 7B–9B 判定器被否决 → 触发 Spike 13 §1.1 降级链**第 2 级**：
  **字面 rubric 预过滤 + 人工兜底**；自动 LLM 预过滤层在本机暂时缺席。
- Spike 13 §3/§8：路由规则与五条验收门槛（强制项绝不 auto-pass、无记录人判不得离开
  pending、每人判落校准语料）。

本模块立场（三条铁律）：
1. **绝不静默 auto-pass**：judge 不可用（本机现状）→ 全部 claim 进 pending_human，
   rubric 红旗只是 reason 标注，不是放行信号；judge 可用 → 也只有「全 supported」
   才 auto-pass，且进 periodic_audit 抽样池（Spike 13 §3）。
2. **不信任模型自总结**：overall 一律由 aggregate() 从 atomic_facts 确定性推导；
   atomic_facts 为空 = 强制人审（forced_empty_atomic），绝不采用模型自报的 overall 放行。
3. **R11 独立预算**：蒸馏人审是独立预算（不占 decay 复审预算）；F_CAP_RATIO 只封顶
   「抽检 + 审计」这类可延后项，**强制项（矛盾/空分解）无预算上限**——安全关键。

校准语料（Spike 13 §7 最小实现）：不建新表。judge_raw 非空且已有人判的 claim 行
本身就是语料（judge 输出与人判同 row，confirm=judge 判对、reject/edit=judge 判错），
经 ``calibration_corpus(store)`` 查询导出。

schema：D9 六字段已在 0001 基线（faithfulness_status/faithfulness_route/judge_raw/
judge_model/human_verdict/human_verdict_at + 枚举 + 索引），本模块零迁移。
"""
from __future__ import annotations

import random
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Optional, Protocol
from uuid import UUID

from pydantic import BaseModel, Field

from . import tuning
from .repository.models import Claim
from .repository.protocols import Storage

# ---------------------------------------------------------------- 状态/路由常量
# （与 0001 基线 DB 枚举/CHECK 同值域；改动须连 migration 一起改）

FAITHFULNESS_STATUSES = (
    "auto_passed", "pending_human", "human_confirmed", "human_rejected", "sampled_pending",
)
FAITHFULNESS_ROUTES = (
    "forced_contradicted", "forced_empty_atomic", "sampled_unsupported",
    "periodic_audit", "auto_supported", "human_only",
)
HUMAN_VERDICTS = ("confirm", "reject", "edit")

# judge 调用契约（Spike 12 llm_fn 同源）：输入 (prompt, system)，输出 Judgment。
# 换上合规判定模型（更快硬件/离盒/云端 opt-in）时零改动接入。
JudgeFn = Callable[[str, str], "Judgment"]


# ---------------------------------------------------------------- judge seam（Spike 12 移植）

FactVerdict = str  # supported | unsupported | contradicted
OverallVerdict = str  # supported | partial | unsupported | contradicted


class AtomicFact(BaseModel):
    """一条原子事实 + 逐条判定（Spike 12 合同同构）。"""

    fact: str
    verdict: FactVerdict
    evidence: str = ""  # 支撑/反对它的来源 id，找不到写「无」


class Judgment(BaseModel):
    """单条 claim 的分解式判定结果。overall 仅在 atomic_facts 为空时作回退，
    本模块路由一律用 aggregate() 重算，不信任自报值。"""

    atomic_facts: list[AtomicFact] = Field(default_factory=list)
    overall: OverallVerdict = "unsupported"
    reason: str = ""


def aggregate(facts: list[AtomicFact]) -> Optional[OverallVerdict]:
    """从逐条原子事实标签**确定性推导** overall（Spike 12 同款）。

    返回 None 表示没有事实可推导（调用方应强制人审，不许采信模型自报 overall）。
    """
    if not facts:
        return None
    vs = {f.verdict for f in facts}
    if "contradicted" in vs:
        return "contradicted"
    if "unsupported" in vs:
        return "partial" if "supported" in vs else "unsupported"
    return "supported"


# 小模型不产 JSON（13b-probe 实证）：防御式解析——抽首个 {...} 块 + pydantic 校验。
_JSON_RE = re.compile(r"\{.*\}", re.S)


def parse_judgment(content: str) -> Judgment:
    m = _JSON_RE.search(content or "")
    if not m:
        raise ValueError("no-json-block-in-output")
    return Judgment.model_validate_json(m.group(0))


JUDGE_SYSTEM = (
    "你是严格的忠实度审查员，服务于一个个人知识复利工具。"
    "一条「claim」是由 LLM 从原始笔记中蒸馏/综合出的陈述。你的任务：判断这条 claim "
    "是否忠实于给定的【来源】——即 claim 中的每一个事实断言，是否都能由来源明确支持，"
    "或可由来源合理推出；凡是来源未提及、无法推出、或明确反对的，都算不忠实。"
    "你只依据给出的来源判断，不得引入来源之外的常识或外部知识。只输出要求的字段。"
)


def build_judge_prompt(claim: str, sources: list[dict]) -> str:
    """构造分解式判定 prompt（Spike 12 build_prompt 同款）。"""
    src_block = "\n".join(
        f"[{s['id']}] {s.get('title', '')}：{s['content']}" for s in sources
    )
    return (
        f"【来源】\n{src_block}\n\n"
        f"【待判定 claim】\n{claim}\n\n"
        f"【任务】\n"
        f"1. 把 claim 拆成若干「原子事实」（每条是一个不可再分的事实断言）。\n"
        f"2. 对每条原子事实，严格依据【来源】判定：\n"
        f"   - supported：来源明确支持或可合理推出；\n"
        f"   - unsupported：来源未提及、无法推出；\n"
        f"   - contradicted：来源明确反对（如数字、实体、结论冲突）。\n"
        f"3. 每条标注 evidence：支撑或反对它的来源 id；若都找不到写「无」。\n"
        f"4. overall 由事实标签推导（我们也会自己重算，你可填可空）。\n"
        f"5. reason：一句话说明最关键的依据。\n"
        f"逐条核验，宁可标 unsupported 也不要脑补支持。"
    )


def judge_claim(llm_fn: JudgeFn, claim: str, sources: list[dict],
                retries: int = 1) -> Judgment:
    """对单条 claim 跑分解式判定：有事实则用推导 overall，空分解重试一次。

    与 Spike 12 唯一差异：重试耗尽后**原样返回**（空 atomic_facts 会由路由层
    判为 forced_empty_atomic 强制人审），绝不采信自报 overall 放行。
    """
    prompt = build_judge_prompt(claim, sources)
    last: Optional[Judgment] = None
    for _ in range(retries + 1):
        j = llm_fn(prompt, JUDGE_SYSTEM)
        if aggregate(j.atomic_facts) is not None:
            return Judgment(atomic_facts=j.atomic_facts,
                            overall=aggregate(j.atomic_facts), reason=j.reason)
        last = j
    assert last is not None
    return last


# ---------------------------------------------------------------- 字面 rubric（Spike 10 移植）

_PUNCT = re.compile(r"[\s，。；：、！？,.!?:;\"'“”‘’（）()【】\[\]—\-]+")


def _normalize(text: str) -> str:
    return _PUNCT.sub("", text or "")


def _ngrams(text: str, n: int = 3) -> set[str]:
    t = _normalize(text)
    if len(t) < n:
        return {t} if t else set()
    return {t[i:i + n] for i in range(len(t) - n + 1)}


def _lcs_length(a: str, b: str) -> int:
    """最长公共子串长度（输入截断，保持廉价）。"""
    a, b = _normalize(a)[:600], _normalize(b)[:600]
    if not a or not b:
        return 0
    prev = [0] * (len(b) + 1)
    best = 0
    for ca in a:
        cur = [0] * (len(b) + 1)
        for j, cb in enumerate(b, start=1):
            if ca == cb:
                cur[j] = prev[j - 1] + 1
                if cur[j] > best:
                    best = cur[j]
        prev = cur
    return best


def verbatim_rate(claim: str, source_texts: list[str]) -> float:
    """claim 被字面照抄的比例（0..1）；高 = 抄袭非抽象。"""
    body = _normalize(claim)
    if not body:
        return 0.0
    return min(1.0, max((_lcs_length(claim, s) for s in source_texts), default=0) / len(body))


def overlap(claim: str, source_texts: list[str]) -> float:
    """3-gram 重叠率；抓 LCS 漏掉的拼接复述（patchwork）。"""
    cg = _ngrams(claim, 3)
    if not cg:
        return 0.0
    src: set[str] = set()
    for s in source_texts:
        src |= _ngrams(s, 3)
    return len(cg & src) / len(cg)


def rubric_flags(claim_text: str, source_texts: list[str]) -> list[str]:
    """字面 rubric 预过滤：返回确定性红旗标签（可空）。

    ⚠️ Spike 10 盲点（显式记账，不静默忽略）：这些红旗**不是忠实度判定**——
    内容幻觉（无据编造）的字面重叠同样低，rubric 分不清「好抽象」与「编造」。
    红旗只作 pending_human 的 reason 标注，帮助人审排序，绝不构成放行依据。
    """
    flags: list[str] = []
    texts = [t for t in source_texts if (t or "").strip()]
    if not texts:
        # evidence_refs 是 schema 级 NOT NULL，但来源文本可能空：同样只是标注。
        return ["rubric_no_source_text"]
    v = verbatim_rate(claim_text, texts)
    o = overlap(claim_text, texts)
    if v > float(tuning.get("FAITH_RUBRIC_VERBATIM_MAX")):
        flags.append(f"rubric_verbatim_{v:.2f}")
    if o > float(tuning.get("FAITH_RUBRIC_OVERLAP_MAX")):
        flags.append(f"rubric_overlap_{o:.2f}")
    return flags


# ---------------------------------------------------------------- 路由（Spike 13 §3 + 降级链）

@dataclass
class RouteDecision:
    """一条 claim 的路由结果：写入 D9 字段的值 + 供人审展示的 reason。

    - status ∈ FAITHFULNESS_STATUSES；route ∈ FAITHFULNESS_ROUTES
    - judge_raw / judge_model：judge 可用时携带（可复现/离盒追溯）；不可用时 None
    - flags：字面 rubric 红旗（仅标注，不构成放行依据）
    """

    claim_id: UUID
    status: str
    route: str
    judge_raw: Optional[dict] = None
    judge_model: Optional[str] = None
    flags: list[str] = field(default_factory=list)
    reason: str = ""


class ClaimSourceProvider(Protocol):
    """claim → 来源文本 的供给 seam（存储无关；调用方负责取节点内容）。"""

    def __call__(self, claim: Claim) -> list[dict]:  # [{id,title,content}, ...]
        ...


def route_claim(
    claim: Claim,
    sources: list[dict],
    *,
    judge_fn: Optional[JudgeFn] = None,
    judge_model: Optional[str] = None,
    rng: Optional[random.Random] = None,
) -> RouteDecision:
    """对一条 claim 做路由决策（纯函数，不落库）。

    双模式：
    - judge_fn=None（本机现状，13b-probe 实证降级）→ pending_human/human_only。
      rubric 红旗进 flags+reason 辅助人审排序，**不改变状态**。
    - judge_fn 可用 → Spike 13 §3 四分支，overall 由 aggregate() 推导：
        空分解 → forced_empty_atomic（pending_human）
        任一 contradicted → forced_contradicted（pending_human）
        混 unsupported（无 contradicted）→ sampled_unsupported：
            以 FAITH_R_UNSUPPORTED 抽样；抽中 → pending_human，未抽中 → sampled_pending
        全 supported → auto_supported：以 FAITH_AUDIT_RATE 抽审计；
            抽中 → pending_human（periodic_audit），未抽中 → auto_passed
    """
    rng = rng or random.Random()
    texts = [s.get("content", "") for s in sources]
    flags = rubric_flags(claim.statement, texts)

    if judge_fn is None:
        # 降级链第 2 级：judge 不可用 → 全人工（Spike 13 §1 安全降级：不漏幻觉的唯一保证）。
        # flags 持久化进 judge_raw（jsonb 自由结构），供 pending 队列排序与追溯。
        reason = "judge 不可用（13b-probe：本机 4B/9B 双否决），全人工兜底"
        if flags:
            reason += "；红旗：" + ", ".join(flags)
        return RouteDecision(
            claim_id=claim.id, status="pending_human", route="human_only",
            judge_raw={"flags": flags, "mode": "human_only"},
            judge_model=None, flags=flags, reason=reason,
        )

    j = judge_claim(judge_fn, claim.statement, sources)
    derived = aggregate(j.atomic_facts)
    jr = j.model_dump()
    jr["flags"] = flags  # rubric 红旗随 judge_raw 留痕（Spike 13 §5 judge_raw 为自由 jsonb）
    common = dict(claim_id=claim.id, judge_raw=jr, judge_model=judge_model, flags=flags)

    if derived is None:
        # 空分解 = 高不确定（拆不出事实），强制人审，绝不采信自报 overall。
        return RouteDecision(status="pending_human", route="forced_empty_atomic",
                             reason="judge 空分解（拆不出原子事实），强制人审", **common)
    if derived == "contradicted":
        return RouteDecision(status="pending_human", route="forced_contradicted",
                             reason="judge 判定存在与来源冲突的原子事实，强制人审", **common)
    if derived in ("unsupported", "partial"):
        if rng.random() < float(tuning.get("FAITH_R_UNSUPPORTED")):
            return RouteDecision(status="pending_human", route="sampled_unsupported",
                                 reason=f"judge={derived}，抽检命中（R_unsupported）", **common)
        # 未抽中：sampled_pending 留痕（不静默放行，可被审计/人工翻查）。
        return RouteDecision(status="sampled_pending", route="sampled_unsupported",
                             reason=f"judge={derived}，抽检未命中，留痕待审计", **common)
    # 全 supported：auto_pass + 周期审计抽样（auto-pass 也可能错，估计真实危险漏检率）。
    if rng.random() < float(tuning.get("FAITH_AUDIT_RATE")):
        return RouteDecision(status="pending_human", route="periodic_audit",
                             reason="judge=supported，周期审计抽样命中", **common)
    return RouteDecision(status="auto_passed", route="auto_supported",
                         reason="judge=supported，显式 auto-pass（judge_raw 留痕）", **common)


# ---------------------------------------------------------------- store 编排（落库 + 消费口 + 人审）

def gate_new_claims(
    store: Storage,
    claims: list[Claim],
    source_provider: ClaimSourceProvider,
    *,
    judge_fn: Optional[JudgeFn] = None,
    judge_model: Optional[str] = None,
    rng: Optional[random.Random] = None,
) -> list[RouteDecision]:
    """对新蒸馏/结合产出的 claims 跑闸门并落库 D9 字段（OCC save）。

    验收门槛 ③ 的落点之一：离开本函数时每条 claim 必处于
    「pending_human / sampled_pending / auto_passed(带 judge_raw)」三者之一，
    不存在无记录的放行（human_only 模式下不可能出现 auto_passed）。
    """
    decisions = []
    for c in claims:
        stored = store.claims.get(c.id) if c.id else None
        target = stored if stored is not None else c
        d = route_claim(target, source_provider(target),
                        judge_fn=judge_fn, judge_model=judge_model, rng=rng)
        target.faithfulness_status = d.status
        target.faithfulness_route = d.route
        target.judge_raw = d.judge_raw
        target.judge_model = d.judge_model
        store.claims.save(target)
        d.claim_id = target.id  # 未落库 claim 由 save 分配 id 后回填
        decisions.append(d)
    return decisions


def pending_human_queue(store: Storage, limit: int = 50) -> list[dict]:
    """人工兜底消费口：列出待人审 claims（强制项优先，rubric 红旗加权排序）。

    排序：forced_* 在前，红旗多的在前——注意预算语义（R11 独立预算）下强制项
    永不因预算被丢弃，此处只影响展示顺序。
    """
    items = store.claims.list_by_status("pending_human")
    def _rank(c: Claim) -> tuple:
        forced = 0 if (c.faithfulness_route or "").startswith("forced") else 1
        n_flags = sum(1 for f in _flags_of(c) if f.startswith("rubric"))
        return (forced, -n_flags)
    items.sort(key=_rank)
    return [_claim_to_dict(c) for c in items[:limit]]


def _flags_of(claim: Claim) -> list[str]:
    """从 judge_raw 还原红旗（两种模式都把 flags 存进 judge_raw，见 route_claim）。"""
    if isinstance(claim.judge_raw, dict):
        return [f for f in (claim.judge_raw.get("flags") or []) if isinstance(f, str)]
    return []


def adjudicate(
    store: Storage,
    claim_id,
    verdict: str,
    *,
    now: Optional[datetime] = None,
) -> dict:
    """人工兜底裁决（Spike 13 §3 interrupt/resume 的同步最小版）。

    verdict ∈ {confirm, reject, edit}：
      confirm → human_confirmed；reject/edit → human_rejected。
    同时把裁决时刻写 human_verdict_at（校准语料的「有人判」标志）。

    校准语料（Spike 13 §7 最小实现）：不建新表——judge_raw 非空且 human_verdict
    非空的 claim 行即语料，经 calibration_corpus() 导出。
    """
    now = now or datetime.now(timezone.utc)
    if isinstance(claim_id, str):
        claim_id = UUID(claim_id)
    if verdict not in HUMAN_VERDICTS:
        raise ValueError(f"verdict 必须 ∈ {HUMAN_VERDICTS}，收到 {verdict!r}")
    claim = store.claims.get(claim_id)
    if claim is None:
        raise ValueError(f"claim {claim_id} not found")
    if claim.faithfulness_status not in ("pending_human", "sampled_pending"):
        raise ValueError(
            f"claim {claim_id} 状态为 {claim.faithfulness_status}，只有 pending 状态可裁决"
            "（验收③：无记录人判不得离开 pending，终态不可二次裁决）")
    claim.human_verdict = verdict
    claim.human_verdict_at = now
    claim.faithfulness_status = "human_confirmed" if verdict == "confirm" else "human_rejected"
    store.claims.save(claim)
    return dict(claim_id=str(claim_id), verdict=verdict,
                faithfulness_status=claim.faithfulness_status,
                calibration_usable=bool(claim.judge_raw))


def calibration_corpus(store: Storage) -> list[dict]:
    """导出校准语料（Spike 13 §7）：judge 真实跑过且已有人判的 claim 行。

    判定语义：judge_correct = 「judge 认为忠实」与「人判忠实」的一致性——
      judge=supported 且人 confirm → 判对；judge=supported 且人 reject/edit
      → 判错 = **真实危险漏检**（幻觉被放过）；judge 判 bad 而人 confirm → 误杀。
    语料判据：judge_raw 含 atomic_facts（真实 Judgment 形状）。human_only 模式的
    judge_raw 只存 flags（无 atomic_facts），无 judge 可对照，不进语料。
    生产人判流量自然生长语料，无需单独标注工程。
    """
    out = []
    for status in ("human_confirmed", "human_rejected"):
        for c in store.claims.list_by_status(status):
            raw = c.judge_raw if isinstance(c.judge_raw, dict) else {}
            if "atomic_facts" not in raw:
                continue  # judge 未真实运行（human_only flags 留痕），无对照价值
            judge_overall = raw.get("overall")
            human_faithful = (c.human_verdict == "confirm")
            out.append(dict(
                claim_id=str(c.id),
                judge_overall=judge_overall,
                judge_atomic=[f.get("verdict") for f in raw.get("atomic_facts", [])],
                human_verdict=c.human_verdict,
                judge_correct=((judge_overall == "supported") == human_faithful),
            ))
    return out


def _claim_to_dict(c: Claim) -> dict:
    return dict(
        id=str(c.id),
        statement=c.statement,
        level=c.level,
        evidence_refs=[str(u) for u in c.evidence_refs],
        faithfulness_status=c.faithfulness_status,
        faithfulness_route=c.faithfulness_route,
        judge_model=c.judge_model,
        human_verdict=c.human_verdict,
        judge_reason=((c.judge_raw or {}).get("reason") if isinstance(c.judge_raw, dict) else None),
        created_at=(c.created_at.isoformat() if c.created_at else None),
    )
