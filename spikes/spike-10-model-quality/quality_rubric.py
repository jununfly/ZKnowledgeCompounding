"""Spike 10: automatic quality rubric for distillation / combine products.

WHY THIS EXISTS: spike 04/05 concluded "1.5B output is near-verbatim / summary
piling" from *subjective reading*. That is not falsifiable — it cannot tell you whether
a new model is actually better. This module turns the failure modes that were observed
into numbers that can be computed on any artifact, so a re-test produces a verdict
instead of an impression.

Metrics (all automatic; no LLM judge, because a small model judging itself is circular):

  verbatim_rate      longest-common-substring ratio between a claim and its sources.
                     HIGH = the claim was copied, not abstracted.  [GATE]
  cross_source_rate  share of claims citing >= 2 sources. LOW = "one claim per source",
                     the exact spike 05 failure.  [GATE]
  structural_fit     required/expected fields actually filled.  [GATE]
  overlap            literal 3-gram overlap with cited sources.
                     [GATE: catches PATCHWORK verbatim that LCS misses]

SECOND MEASUREMENT FINDING (recorded): LCS alone does NOT catch "patchwork copying" —
a claim assembled by stitching several phrases from one source has a modest longest
common substring but a very high 3-gram overlap. Observed on arm B: a claim that is
essentially source s2 reworded-and-stitched scored verbatim 0.48 (would PASS a 0.50
gate) while its overlap was far higher. So `overlap` is a second, independent gate
(OVERLAP_MAX), not merely descriptive.
  citation_hit       whether cited sources are the most literally similar.  [WEAK]

KNOWN BLIND SPOT (recorded, not silently ignored): faithfulness / hallucination CANNOT
be measured literally. A well-abstracted claim SHOULD use words absent from its sources,
so literal overlap is low for both "good abstraction" and "ungrounded invention" — the
metric cannot separate them. Verified on this corpus: a copied sentence scores
verbatim 1.00 / overlap 1.00; a good abstraction scores verbatim 0.18 / overlap 0.12.
Therefore `overlap` is reported for transparency but is NOT a pass/fail gate; detecting
ungrounded claims needs an LLM judge or a human (see README "仍 open").

Thresholds are PLACEHOLDERS (flagged as such) — they must be calibrated against a
human-labelled sample before being used as acceptance gates.
"""
from __future__ import annotations

import re

# --- placeholder thresholds (calibrate on labelled data before using as a gate) -------
VERBATIM_MAX = 0.50          # above this a claim counts as copied (single long lift)
OVERLAP_MAX = 0.70           # above this it counts as patchwork copying (see docstring)
CROSS_SOURCE_MIN = 0.30      # share of claims that should synthesise >= 2 sources
CROSS_SOURCE_MIN_CLAIMS = 2  # ... AND at least this many cross-source claims in absolute
                             # terms (a rate alone is gameable by emitting few claims)
FAITHFULNESS_MIN = 0.40      # share of claim n-grams that must be grounded
STRUCTURAL_MIN = 1.00        # expected fields must all be filled

_PUNCT = re.compile(r"[\s，。；：、！？,.!?:;\"'“”‘’（）()【】\[\]—\-]+")


def normalize(text: str) -> str:
    return _PUNCT.sub("", text or "")


def ngrams(text: str, n: int = 3) -> set[str]:
    t = normalize(text)
    if len(t) < n:
        return {t} if t else set()
    return {t[i:i + n] for i in range(len(t) - n + 1)}


def _lcs_length(a: str, b: str) -> int:
    """Longest common substring length (capped input to keep it cheap)."""
    a, b = normalize(a)[:600], normalize(b)[:600]
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
    """How much of the claim is literally lifted from a source (0..1)."""
    body = normalize(claim)
    if not body:
        return 0.0
    return min(1.0, max((_lcs_length(claim, s) for s in source_texts), default=0) / len(body))


def overlap(claim: str, source_texts: list[str]) -> float:
    """DESCRIPTIVE ONLY — see the blind-spot note in the module docstring."""
    cg = ngrams(claim, 3)
    if not cg:
        return 0.0
    src: set[str] = set()
    for s in source_texts:
        src |= ngrams(s, 3)
    return len(cg & src) / len(cg)


def citation_hit(claim: str, cited_texts: list[str], all_sources: list[dict]) -> float:
    """WEAK signal: are the cited sources the most literally similar ones?

    Returns the share of cited sources that fall in the top-k most similar
    (k = number of citations). Low = the model cited the wrong source — the spike 05
    symptom "local 层错填来源 id". Weak because literal similarity is a poor proxy for
    relevance to an abstract claim.
    """
    if not cited_texts:
        return 0.0
    cg = ngrams(claim, 3)
    if not cg:
        return 0.0
    sims = []
    for s in all_sources:
        sg = ngrams(s["content"], 3)
        sims.append((len(cg & sg) / len(cg | sg) if (cg | sg) else 0.0, s["content"]))
    sims.sort(key=lambda x: x[0], reverse=True)
    top = {t for _, t in sims[: len(cited_texts)]}
    return sum(1 for t in cited_texts if t in top) / len(cited_texts)


# ------------------------------------------------------------------ artifact scoring
def score_artifact(artifact: dict, sources: list[dict]) -> dict:
    """Score a combine product (spike 05 ModelingArtifact shape)."""
    by_id = {s["id"]: s["content"] for s in sources}
    claims = artifact.get("claims", []) or []

    verbatim, faithful, multi, hits = [], [], 0, []
    for c in claims:
        texts = [by_id[e] for e in c.get("evidence_ids", []) if e in by_id]
        if len(c.get("evidence_ids", [])) >= 2:
            multi += 1
        if texts:
            verbatim.append(verbatim_rate(c.get("statement", ""), texts))
            faithful.append(overlap(c.get("statement", ""), texts))
            hits.append(citation_hit(c.get("statement", ""), texts, sources))

    n = max(1, len(claims))
    expected = {
        "claims": bool(claims),
        "local": bool(artifact.get("local")),
        "global": bool(artifact.get("global") or artifact.get("global_insights")),
    }
    if artifact.get("kind") == "methodology":
        expected["methodology_steps"] = bool(artifact.get("methodology_steps"))

    return dict(
        n_claims=len(claims),
        n_cross_source=multi,
        verbatim_rate=round(sum(verbatim) / max(1, len(verbatim)), 3) if verbatim else None,
        overlap=round(sum(faithful) / max(1, len(faithful)), 3) if faithful else None,
        citation_hit=round(sum(hits) / max(1, len(hits)), 3) if hits else None,
        cross_source_rate=round(multi / n, 3),
        structural_fit=round(sum(1 for v in expected.values() if v) / len(expected), 3),
        structural_detail=expected,
    )


def score_claim(claim: dict, sources: list[dict]) -> dict:
    """Score a distillation product (spike 04 ClaimDraft shape)."""
    texts = [s["content"] for s in sources]
    body = normalize(claim.get("statement", ""))
    filled = {
        "statement": bool(claim.get("statement")),
        "level": bool(claim.get("level")),
        "topic": bool(claim.get("topic")),
        "reasoning": bool(claim.get("reasoning")),
        "confidence": claim.get("confidence") is not None,
    }
    return dict(
        verbatim_rate=round(verbatim_rate(claim.get("statement", ""), texts), 3),
        overlap=round(overlap(claim.get("statement", ""), texts), 3),
        abstraction=round(1 - verbatim_rate(claim.get("statement", ""), texts), 3),
        structural_fit=round(sum(1 for v in filled.values() if v) / len(filled), 3),
        structural_detail=filled,
    )


def verdict(scores: dict, kind: str = "artifact") -> dict:
    """Turn numbers into a pass/fail per dimension (thresholds are placeholders)."""
    # NOTE: `citation_hit` is deliberately NOT a gate (weak literal-similarity proxy).
    checks = {
        "not_verbatim": (scores.get("verbatim_rate") is not None
                         and scores["verbatim_rate"] <= VERBATIM_MAX),
        "not_patchwork": (scores.get("overlap") is None
                          or scores["overlap"] <= OVERLAP_MAX),
        "structurally_complete": (scores.get("structural_fit", 0) >= STRUCTURAL_MIN),
    }
    if kind == "artifact":
        # THIRD MEASUREMENT FINDING: a RATE alone is gameable by emitting few claims.
        # Observed: arm A produced exactly 1 claim citing 2 sources -> cross_source_rate
        # 1.0, i.e. it "beat" arms that produced 3-5 claims. Require an absolute floor too.
        checks["cross_source"] = (
            scores.get("cross_source_rate", 0) >= CROSS_SOURCE_MIN
            and scores.get("n_cross_source", 0) >= CROSS_SOURCE_MIN_CLAIMS
        )
    return dict(checks=checks, all_pass=all(checks.values()))
