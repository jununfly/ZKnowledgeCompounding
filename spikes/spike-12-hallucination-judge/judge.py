"""Spike 12: hallucination / faithfulness judge (LLM-as-judge).

CORE QUESTION (open item from spike 10 §6/§9 and spike 11 §6):
  The literal rubric (verbatim / overlap / citation_hit) CANNOT tell whether a claim's
  CONTENT is actually supported by its cited sources. A claim may cite valid source ids
  yet assert something the sources never say (CONTENT HALLUCINATION). This module closes
  that gap with an LLM-as-judge, and answers the deployment question: can the MVP judge
  model (qwen3.5:4b-mlx) serve as an automated faithfulness gate, or must we use
  human-in-the-loop / a larger judge model?

DESIGN — DECOMPOSE-THEN-VERIFY in a single structured call:
  We do NOT trust the model's self-summary. We force it to split the claim into atomic
  facts and label each supported / unsupported / contradicted against the FULL source
  set, then we DERIVE the overall verdict deterministically from the per-fact labels.
  This pushes the hard "is this faithful?" question down into many easier
  "is THIS atomic fact in the sources?" sub-questions, and makes dangerous misses
  traceable (which atomic fact was mislabeled).

SMALL-MODEL RISK (the thing we are measuring):
  4B judges may be sycophantic / over-trusting and let hallucinations pass — the
  DANGEROUS FALSE NEGATIVE (truth=unsupported/contradicted judged "supported"). We
  measure that rate explicitly; it is the only metric that decides automation.

CONTRACT (injectable so the mechanism is unit-testable without a model):
  judge_claim(llm_fn, claim, sources) -> Judgment
  llm_fn(prompt, system) -> Judgment
"""
from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path
from typing import Callable, Literal

from pydantic import BaseModel, Field

# --- reuse spike 10's frozen corpus (no copy drift) -------------------------
_HERE = Path(__file__).resolve().parent
_SPIKES = _HERE.parent


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod  # register BEFORE exec: @dataclass needs sys.modules[__name__]
    spec.loader.exec_module(mod)
    return mod


corpus = _load("s12_corpus", _SPIKES / "spike-10-model-quality" / "corpus.py")

FactVerdict = Literal["supported", "unsupported", "contradicted"]  # atomic-fact level
OverallVerdict = Literal["supported", "partial", "unsupported", "contradicted"]  # derived


# ----------------------------------------------------------------- models
class AtomicFact(BaseModel):
    fact: str
    verdict: FactVerdict
    evidence: str = ""  # supporting/contradicting source id(s), or "无"


class Judgment(BaseModel):
    atomic_facts: list[AtomicFact] = Field(default_factory=list)
    overall: OverallVerdict = "unsupported"  # only used when atomic_facts is empty
    reason: str = ""


# Small local models (qwen3.5:4b via Ollama) do NOT reliably emit strict JSON for this
# decomposed task — they return Markdown prose. instructor.Mode.JSON hangs on the
# reasoning stream. So we parse defensively: pull the first {...} block and validate;
# if the model only emitted prose, the caller may fall back (see run_spike12.py).
_JSON_RE = re.compile(r"\{.*\}", re.S)


def parse_judgment(content: str) -> Judgment:
    m = _JSON_RE.search(content or "")
    if not m:
        raise ValueError("no-json-block-in-output")
    return Judgment.model_validate_json(m.group(0))


SYSTEM = (
    "你是严格的忠实度审查员，服务于一个个人知识复利工具。"
    "一条「claim」是由 LLM 从原始笔记中蒸馏/综合出的陈述。你的任务：判断这条 claim "
    "是否忠实于给定的【来源】——即 claim 中的每一个事实断言，是否都能由来源明确支持，"
    "或可由来源合理推出；凡是来源未提及、无法推出、或明确反对的，都算不忠实。"
    "你只依据给出的来源判断，不得引入来源之外的常识或外部知识。只输出要求的字段。"
)


def build_prompt(claim: str, sources: list[dict]) -> str:
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


def claim_from_prompt(prompt: str) -> str:
    """Recover the claim text from a prompt built by build_prompt().

    The LLM contract only exposes (prompt, system) to llm_fn — just like a real
    model. A faithful oracle/stub therefore must read the claim back out of the
    prompt. This helper makes that exact and reusable (also handy for debugging)."""
    marker = "【待判定 claim】\n"
    end = "\n\n【任务】"
    if marker in prompt and end in prompt:
        return prompt.split(marker, 1)[1].split(end, 1)[0]
    return ""


def aggregate(facts: list[AtomicFact]) -> OverallVerdict | None:
    """Derive the overall verdict deterministically from per-fact labels.

    Returns None when there are no facts (caller should fall back to the model's
    self-reported `overall`, or retry).
    """
    if not facts:
        return None
    vs = {f.verdict for f in facts}
    if "contradicted" in vs:
        return "contradicted"
    if "unsupported" in vs:
        return "partial" if "supported" in vs else "unsupported"
    return "supported"


def judge_claim(llm_fn: Callable[[str, str], Judgment], claim: str,
               sources: list[dict], retries: int = 1) -> Judgment:
    """Run the judge on one claim; derive overall from atomic facts, never trust
    the model's self-summary when facts are present. Retries only on empty facts."""
    prompt = build_prompt(claim, sources)
    last: Judgment | None = None
    for _ in range(retries + 1):
        j = llm_fn(prompt, SYSTEM)
        derived = aggregate(j.atomic_facts)
        if derived is not None:
            return Judgment(atomic_facts=j.atomic_facts, overall=derived, reason=j.reason)
        last = j  # empty atomic_facts: fall back to provided overall, retry once
    assert last is not None
    return last


def judge_artifact(llm_fn: Callable[[str, str], Judgment], artifact: dict,
                  sources_by_id: dict[str, dict]) -> dict:
    """Judge every claim in a combine/distill artifact against its cited sources
    (fall back to the full set if citations are empty)."""
    per: list[dict] = []
    for c in artifact.get("claims", []) or []:
        ids = c.get("evidence_ids", []) or []
        cited = [sources_by_id[i] for i in ids if i in sources_by_id]
        if not cited:
            cited = list(sources_by_id.values())
        j = judge_claim(llm_fn, c.get("statement", ""), cited)
        per.append({"statement": c.get("statement", ""), "judgment": j.overall,
                    "atomic": [f.model_dump() for f in j.atomic_facts]})
    n = max(1, len(per))
    faithful = sum(1 for p in per if p["judgment"] == "supported")
    return {"n_claims": len(per), "faithful_rate": round(faithful / n, 3), "per": per}


# ----------------------------------------------------------------- golden set
# Each example carries a human-authored decomposition; `truth` is DERIVED from it via
# aggregate(), guaranteeing label self-consistency (no manual label drift).
GOLDEN: list[dict] = [
    # ---- supported (5): content genuinely grounded in sources ----
    {"id": "g1", "claim": "安全评审打回客户端鉴权，要求所有权限判断必须在服务端完成。",
     "decomp": [("安全评审打回客户端鉴权并要求权限判断在服务端完成", "supported")]},
    {"id": "g2", "claim": "外部依赖的到期时间不是我们的排期时间。",
     "decomp": [("外部依赖的到期时间不是我们的排期时间", "supported")]},
    {"id": "g3", "claim": "所有先临时绕过、后面再补的决定，最后都变成系统的长期负担，临时方案上线后再没人主动拆掉。",
     "decomp": [("所有临时绕过后面再补的决定最后都变成系统长期负担，上线后没人主动拆", "supported")]},
    {"id": "g4", "claim": "把压测从上线前提前到设计评审阶段，可在改动成本几乎为零时发现连接池瓶颈。",
     "decomp": [("压测提前到设计评审阶段可在改动成本几乎为零时发现连接池瓶颈", "supported")]},
    {"id": "g5", "claim": "团队约定临时绕过须记入技术债台账并带责任人和清理时间，两个月里三分之一被真正清理。",
     "decomp": [("临时绕过须记入技术债台账带责任人和清理时间，两个月里三分之一被清理", "supported")]},
    # ---- contradicted (5): claim asserts facts the sources explicitly oppose ----
    {"id": "g6", "claim": "安全评审要求所有权限判断必须在客户端完成。",
     "decomp": [("安全评审要求所有权限判断必须在客户端完成", "contradicted")]},
    {"id": "g7", "claim": "第三方 SDK 升级被动返工，整整花了三周。",
     "decomp": [("第三方 SDK 升级被动返工花了三周", "contradicted")]},
    {"id": "g8", "claim": "台账里二分之一的临时绕过被真正清理了。",
     "decomp": [("台账里二分之一的临时绕过被真正清理了", "contradicted")]},
    {"id": "g9", "claim": "复盘近五个项目，发现临时绕过变长期负担的共性。",
     "decomp": [("复盘近五个项目发现临时绕过变长期负担的共性", "contradicted")]},
    {"id": "g10", "claim": "在设计阶段发现的是内存泄漏瓶颈。",
     "decomp": [("设计阶段发现的是内存泄漏瓶颈", "contradicted")]},
    # ---- partial (3): supported fact mixed with an unsupported one ----
    {"id": "g11", "claim": "安全评审打回客户端鉴权，并要求所有代码评审必须在服务端完成。",
     "decomp": [("安全评审打回客户端鉴权并要求权限判断在服务端完成", "supported"),
                ("要求所有代码评审必须在服务端完成", "unsupported")]},
    {"id": "g12", "claim": "外部依赖到期不是我们的排期时间，因此应当提前半年升级。",
     "decomp": [("外部依赖的到期时间不是我们的排期时间", "supported"),
                ("因此应当提前半年升级", "unsupported")]},
    {"id": "g13", "claim": "临时绕过都会变成长期负担，而且它们都被安全评审打回。",
     "decomp": [("所有临时绕过后面再补的决定最后都变成系统长期负担", "supported"),
                ("临时绕过都被安全评审打回", "unsupported")]},
]

for _ex in GOLDEN:
    _ex["truth"] = aggregate([AtomicFact(fact=f, verdict=v) for f, v in _ex["decomp"]])


# ----------------------------------------------------------------- evaluation
def evaluate(llm_fn: Callable[[str, str], Judgment],
             samples: list[dict] | None = None) -> dict:
    """Run the judge over the golden set and report the confusion matrix plus the
    dangerous false-negative rate (the only metric that decides automation)."""
    samples = samples or GOLDEN
    classes = ["supported", "partial", "unsupported", "contradicted"]
    confusion: dict[str, dict[str, int]] = {t: {p: 0 for p in classes} for t in classes}
    rows = []
    for ex in samples:
        j = judge_claim(llm_fn, ex["claim"], corpus.SOURCES)
        pred = j.overall
        truth = ex["truth"]
        confusion[truth][pred] += 1
        rows.append({"id": ex["id"], "truth": truth, "pred": pred,
                     "reason": j.reason,
                     "atomic": [f.model_dump() for f in j.atomic_facts]})

    n = len(samples)
    correct = sum(1 for r in rows if r["truth"] == r["pred"])
    # dangerous FN: truth unsupported/contradicted yet judged "supported"
    danger = [r for r in rows if r["truth"] in ("unsupported", "contradicted")]
    danger_fn = [r for r in danger if r["pred"] == "supported"]
    # hallucination catch: truth != supported judged != supported
    hallu = [r for r in rows if r["truth"] != "supported"]
    hallu_caught = [r for r in hallu if r["pred"] != "supported"]

    return {
        "n": n,
        "accuracy": round(correct / n, 3) if n else None,
        "confusion": confusion,
        "dangerous_false_negative_rate": round(len(danger_fn) / len(danger), 3) if danger else None,
        "hallucination_catch_rate": round(len(hallu_caught) / len(hallu), 3) if hallu else None,
        "rows": rows,
    }


def oracle_fn(prompt: str, system: str) -> Judgment:
    """A perfect judge: returns each example's own ground-truth decomposition.

    Used for sanity (should score 100%) and as the reference in tests. It reads the
    claim back out of the prompt, exactly as a real model would have to."""
    claim = claim_from_prompt(prompt)
    ex = next((e for e in GOLDEN if e["claim"] == claim), None)
    if ex is None:
        return Judgment(atomic_facts=[], overall="unsupported", reason="no-match")
    return Judgment(
        atomic_facts=[AtomicFact(fact=f, verdict=v) for f, v in ex["decomp"]],
        reason="oracle",
    )


if __name__ == "__main__":
    # Smoke check: oracle stub should score perfectly (sanity of the pipeline).
    rep = evaluate(oracle_fn)
    print("oracle smoke:", rep["accuracy"], "danger_FN=",
          rep["dangerous_false_negative_rate"])
